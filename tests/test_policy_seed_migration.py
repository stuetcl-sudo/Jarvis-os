import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from app import config
from app.actions.engine import action_engine
from app.actions.history import initialize_action_tables, list_actions
from app.db import connect, init_db
from app.events.event import Event
from app.events.types import EventTypes
from app.policies.engine import JARVIS_MANAGED_BY, POLICY_SEED_VERSION, initialize_policy_tables, policy_engine
from app.policies.rules import default_policies


def reset_db():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    config.DB_PATH = tmp.name
    init_db()
    initialize_policy_tables()
    initialize_action_tables()
    return Path(tmp.name)


def insert_policy(policy_id, enabled=1, managed_by=None, seed_version=None, retired=0, name="User Policy", actions=None):
    now = "2026-01-01T00:00:00+00:00"
    conn = connect()
    conn.execute(
        """
        INSERT INTO policies (policy_id, name, description, enabled, priority, trigger_event_type, conditions, actions, safety_level, created_at, updated_at, managed_by, seed_version, retired)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            policy_id,
            name,
            "original description",
            enabled,
            999,
            "Test.Event",
            json.dumps({"original": True}),
            json.dumps(actions if actions is not None else [{"type": "ignore"}]),
            "user_safe",
            now,
            now,
            managed_by,
            seed_version,
            retired,
        ),
    )
    conn.commit()
    conn.close()


def get_policy(policy_id):
    return policy_engine.get_policy(policy_id)


def test_fresh_database_receives_current_jarvis_managed_policies():
    path = reset_db()
    try:
        policy_engine.ensure_default_policies()
        policies = {p["policy_id"]: p for p in policy_engine.list_policies()}
        for default in default_policies():
            policy = policies[default["policy_id"]]
            assert policy["managed_by"] == JARVIS_MANAGED_BY
            assert policy["seed_version"] == POLICY_SEED_VERSION
            assert policy["retired"] is False
    finally:
        path.unlink(missing_ok=True)


def test_obsolete_known_policy_is_disabled_retired_and_retained():
    path = reset_db()
    try:
        insert_policy("policy.optional_container_stopped", enabled=1, name="Old optional default")
        policy_engine.ensure_default_policies()
        old = get_policy("policy.optional_container_stopped")
        assert old is not None
        assert old["enabled"] is False
        assert old["retired"] is True
        assert old["managed_by"] == JARVIS_MANAGED_BY
    finally:
        path.unlink(missing_ok=True)


def test_current_policy_preserves_manually_disabled_status_and_updates_content():
    path = reset_db()
    try:
        insert_policy("policy.optional_asset_stopped", enabled=0, managed_by=JARVIS_MANAGED_BY, seed_version=1, retired=0, name="Old current default", actions=[{"type": "ignore"}])
        policy_engine.ensure_default_policies()
        policy = get_policy("policy.optional_asset_stopped")
        assert policy["enabled"] is False
        assert policy["managed_by"] == JARVIS_MANAGED_BY
        assert policy["seed_version"] == POLICY_SEED_VERSION
        assert policy["retired"] is False
        assert policy["name"] != "Old current default"
        assert any(action.get("type") == "recommend_restart" for action in policy["actions"])
    finally:
        path.unlink(missing_ok=True)


def test_arbitrary_user_created_policy_remains_unchanged():
    path = reset_db()
    try:
        insert_policy("policy.user.custom", enabled=1, managed_by=None, name="My Custom Policy", actions=[{"type": "ignore"}])
        policy_engine.ensure_default_policies()
        policy = get_policy("policy.user.custom")
        assert policy["name"] == "My Custom Policy"
        assert policy["enabled"] is True
        assert policy["managed_by"] is None
        assert policy["seed_version"] is None
        assert policy["retired"] is False
        assert policy["conditions"] == {"original": True}
        assert policy["actions"] == [{"type": "ignore"}]
        assert policy["priority"] == 999
        assert policy["safety_level"] == "user_safe"
    finally:
        path.unlink(missing_ok=True)


def test_retired_policy_is_not_evaluated():
    path = reset_db()
    try:
        insert_policy("policy.optional_container_stopped", enabled=1, managed_by=JARVIS_MANAGED_BY, seed_version=1, retired=0)
        policy_engine.ensure_default_policies()
        event = Event(source="test", type=EventTypes.CONTAINER_STOPPED, asset_id="docker:example-app", payload={"asset_id": "docker:example-app", "classification": "optional"})
        decisions = policy_engine.evaluate_event(event)
        assert all(d["policy_id"] != "policy.optional_container_stopped" for d in decisions)
    finally:
        path.unlink(missing_ok=True)


def test_migration_is_idempotent_across_repeated_startup():
    path = reset_db()
    try:
        insert_policy("policy.critical_container_stopped", enabled=1)
        policy_engine.ensure_default_policies()
        first = policy_engine.list_policies()
        policy_engine.ensure_default_policies()
        second = policy_engine.list_policies()
        assert len(first) == len(second)
        assert get_policy("policy.critical_container_stopped")["retired"] is True
    finally:
        path.unlink(missing_ok=True)


def test_duplicate_queue_request_does_not_publish_second_action_queued_event():
    path = reset_db()
    try:
        with patch("app.actions.engine.publish") as publish_mock:
            first = action_engine.queue_action(asset_id="docker:example-app", action_type="docker.start_container", requested_by="test", source="test", reason="test")
            second = action_engine.queue_action(asset_id="docker:example-app", action_type="docker.start_container", requested_by="test", source="test", reason="test")
        assert first["action_id"] == second["action_id"]
        assert first["deduplicated"] is False
        assert second["deduplicated"] is True
        assert len(list_actions(10)) == 1
        queued_events = [call for call in publish_mock.call_args_list if call.args[1] == "Action.Queued"]
        assert len(queued_events) == 1
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    for test in [
        test_fresh_database_receives_current_jarvis_managed_policies,
        test_obsolete_known_policy_is_disabled_retired_and_retained,
        test_current_policy_preserves_manually_disabled_status_and_updates_content,
        test_arbitrary_user_created_policy_remains_unchanged,
        test_retired_policy_is_not_evaluated,
        test_migration_is_idempotent_across_repeated_startup,
        test_duplicate_queue_request_does_not_publish_second_action_queued_event,
    ]:
        test()
    print("Policy seed migration tests OK")
