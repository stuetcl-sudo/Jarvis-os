import json
import sqlite3
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

from app import config
from app.actions.action import Action
from app.actions.engine import action_engine
from app.actions.history import ACTION_SCHEMA, get_action, initialize_action_tables, insert_action
from app.actions.queue import approve_action, cancel_action, deny_action, queue_action
from app.actions.state_machine import claim_approved_action, transition_action
from app.db import connect

ACTIVE_STATUSES = ("queued", "waiting_approval", "approved", "running")


class PublishRecorder:
    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, *args, **kwargs):
        with self.lock:
            self.calls.append((args, kwargs))


def reset_db(initialize=True):
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    config.DB_PATH = tmp.name
    if initialize:
        initialize_action_tables()
    return Path(tmp.name)


def active_rows(asset_id=None, action_type=None):
    clauses = ["status IN ('queued', 'waiting_approval', 'approved', 'running')"]
    params = []
    if asset_id is not None:
        clauses.append("asset_id = ?")
        params.append(asset_id)
    if action_type is not None:
        clauses.append("action_type = ?")
        params.append(action_type)
    conn = connect()
    try:
        return [dict(row) for row in conn.execute(f"SELECT * FROM actions WHERE {' AND '.join(clauses)} ORDER BY action_id", params).fetchall()]
    finally:
        conn.close()


def insert_legacy_row(conn, action_id, status, created_at, asset_id="docker:example-app", action_type="docker.start_container"):
    conn.execute(
        """
        INSERT INTO actions (action_id, created_at, updated_at, requested_by, source, asset_id, action_type, status, priority, requires_approval, approved, approved_by, approved_at, safety_status, reason, explanation, payload, result)
        VALUES (?, ?, ?, 'test', 'test', ?, ?, ?, 100, 1, ?, ?, ?, ?, 'legacy duplicate', 'legacy action', '{}', ?)
        """,
        (
            action_id,
            created_at,
            created_at,
            asset_id,
            action_type,
            status,
            1 if status in {"approved", "running"} else 0,
            "test" if status in {"approved", "running"} else None,
            created_at if status in {"approved", "running"} else None,
            "passed" if status == "running" else "not_checked",
            json.dumps({"legacy": action_id}, sort_keys=True),
        ),
    )


def test_sequential_duplicate_requests_create_one_active_action():
    path = reset_db()
    try:
        first = queue_action(asset_id="docker:example-app", action_type="docker.start_container")
        second = queue_action(asset_id="docker:example-app", action_type="docker.start_container")
        assert first["deduplicated"] is False
        assert second["deduplicated"] is True
        assert first["action_id"] == second["action_id"]
        assert first["status"] == "waiting_approval"
        assert len(active_rows("docker:example-app", "docker.start_container")) == 1
    finally:
        path.unlink(missing_ok=True)


def test_many_concurrent_requests_create_one_action_and_publish_once():
    path = reset_db()
    thread_count = 20
    barrier = threading.Barrier(thread_count + 1)
    results = []
    errors = []
    result_lock = threading.Lock()
    recorder = PublishRecorder()

    def worker():
        try:
            barrier.wait()
            result = action_engine.queue_action(asset_id="docker:example-app", action_type="docker.start_container")
            with result_lock:
                results.append(result)
        except Exception as exc:
            with result_lock:
                errors.append(exc)

    try:
        with patch("app.actions.engine.publish", side_effect=recorder):
            with patch("app.actions.executors.docker.from_env", side_effect=AssertionError("queue tests must not access Docker")):
                threads = [threading.Thread(target=worker) for _ in range(thread_count)]
                for thread in threads:
                    thread.start()
                barrier.wait()
                for thread in threads:
                    thread.join()
        assert errors == []
        assert len(results) == thread_count
        assert len({result["action_id"] for result in results}) == 1
        assert sum(result["deduplicated"] is False for result in results) == 1
        assert sum(result["deduplicated"] is True for result in results) == thread_count - 1
        assert len(active_rows("docker:example-app", "docker.start_container")) == 1
        assert len(recorder.calls) == 1
        assert recorder.calls[0][0][1] == "Action.Queued"
    finally:
        path.unlink(missing_ok=True)


def test_different_assets_and_action_types_can_be_active():
    path = reset_db()
    try:
        one = queue_action(asset_id="docker:one", action_type="docker.start_container")
        two = queue_action(asset_id="docker:two", action_type="docker.start_container")
        other_type = queue_action(asset_id="docker:one", action_type="recommendation.create")
        assert one["deduplicated"] is False
        assert two["deduplicated"] is False
        assert other_type["deduplicated"] is False
        assert len(active_rows()) == 3
    finally:
        path.unlink(missing_ok=True)


def test_terminal_actions_allow_a_later_matching_action():
    path = reset_db()
    try:
        for terminal in ("completed", "failed", "denied", "cancelled"):
            asset_id = f"docker:{terminal}"
            original = queue_action(asset_id=asset_id, action_type="docker.start_container")
            if terminal in {"completed", "failed"}:
                approve_action(original["action_id"])
                claimed = claim_approved_action(original["action_id"])
                assert claimed.changed is True
                transition_action(original["action_id"], terminal)
            elif terminal == "denied":
                deny_action(original["action_id"])
            else:
                cancel_action(original["action_id"])
            replacement = queue_action(asset_id=asset_id, action_type="docker.start_container")
            assert replacement["deduplicated"] is False
            assert replacement["action_id"] != original["action_id"]
            assert len(active_rows(asset_id, "docker.start_container")) == 1
    finally:
        path.unlink(missing_ok=True)


def test_existing_duplicate_rows_are_migrated_without_deletion_and_deterministically():
    path = reset_db(initialize=False)
    try:
        conn = connect()
        conn.execute(ACTION_SCHEMA)
        insert_legacy_row(conn, "running-z", "running", "2026-01-03T00:00:00+00:00")
        insert_legacy_row(conn, "running-b", "running", "2026-01-01T00:00:00+00:00")
        insert_legacy_row(conn, "running-a", "running", "2026-01-01T00:00:00+00:00")
        insert_legacy_row(conn, "approved-a", "approved", "2025-01-01T00:00:00+00:00")
        insert_legacy_row(conn, "waiting-a", "waiting_approval", "2024-01-01T00:00:00+00:00")
        insert_legacy_row(conn, "queued-a", "queued", "2023-01-01T00:00:00+00:00")
        conn.commit()
        before_count = conn.execute("SELECT COUNT(*) AS count FROM actions").fetchone()["count"]
        conn.close()

        initialize_action_tables()

        conn = connect()
        rows = [dict(row) for row in conn.execute("SELECT * FROM actions ORDER BY action_id").fetchall()]
        after_count = len(rows)
        conn.close()
        assert before_count == after_count == 6
        survivor = get_action("running-a")
        assert survivor["status"] == "running"
        assert survivor["explanation"] == "legacy action"
        assert survivor["result"] == {"legacy": "running-a"}
        assert len(active_rows("docker:example-app", "docker.start_container")) == 1
        for row in rows:
            if row["action_id"] == "running-a":
                continue
            migrated = get_action(row["action_id"])
            expected_status = "failed" if row["action_id"].startswith("running-") else "cancelled"
            assert migrated["status"] == expected_status
            assert "Retired by atomic Action Queue deduplication migration" in migrated["explanation"]
            metadata = migrated["result"]["atomic_dedup_migration"]
            assert metadata["retired"] is True
            assert metadata["survivor_action_id"] == "running-a"
            assert metadata["previous_status"] in ACTIVE_STATUSES
            assert migrated["result"]["legacy"] == row["action_id"]
    finally:
        path.unlink(missing_ok=True)


def test_migration_is_idempotent():
    path = reset_db(initialize=False)
    try:
        conn = connect()
        conn.execute(ACTION_SCHEMA)
        insert_legacy_row(conn, "approved-a", "approved", "2026-01-01T00:00:00+00:00")
        insert_legacy_row(conn, "approved-b", "approved", "2026-01-02T00:00:00+00:00")
        conn.commit()
        conn.close()
        initialize_action_tables()
        conn = connect()
        first = [tuple(row) for row in conn.execute("SELECT * FROM actions ORDER BY action_id").fetchall()]
        conn.close()
        initialize_action_tables()
        conn = connect()
        second = [tuple(row) for row in conn.execute("SELECT * FROM actions ORDER BY action_id").fetchall()]
        conn.close()
        assert second == first
    finally:
        path.unlink(missing_ok=True)


def test_unique_index_blocks_direct_duplicate_insert():
    path = reset_db()
    try:
        first = insert_action(Action(requested_by="test", source="test", asset_id="docker:example-app", action_type="docker.start_container", reason="first"))
        try:
            insert_action(Action(requested_by="test", source="test", asset_id="docker:example-app", action_type="docker.start_container", reason="duplicate"))
            raise AssertionError("partial unique index should reject a second active action")
        except sqlite3.IntegrityError:
            pass
        assert get_action(first["action_id"])["status"] == "waiting_approval"
        assert len(active_rows("docker:example-app", "docker.start_container")) == 1
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    for test in [
        test_sequential_duplicate_requests_create_one_active_action,
        test_many_concurrent_requests_create_one_action_and_publish_once,
        test_different_assets_and_action_types_can_be_active,
        test_terminal_actions_allow_a_later_matching_action,
        test_existing_duplicate_rows_are_migrated_without_deletion_and_deterministically,
        test_migration_is_idempotent,
        test_unique_index_blocks_direct_duplicate_insert,
    ]:
        test()
    print("Atomic Action Queue tests OK")
