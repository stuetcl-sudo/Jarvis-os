import json
from typing import Any

from app.actions.action import ACTION_STATUSES, Action, now_iso
from app.db import connect

ACTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    action_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    source TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    requires_approval INTEGER NOT NULL DEFAULT 1,
    approved INTEGER NOT NULL DEFAULT 0,
    approved_by TEXT,
    approved_at TEXT,
    safety_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    explanation TEXT NOT NULL,
    payload TEXT NOT NULL,
    result TEXT NOT NULL
)
"""

ACTIVE_STATUS_SQL = "'queued', 'waiting_approval', 'approved', 'running'"
ACTIVE_ACTION_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_actions_active_asset_type
ON actions(asset_id, action_type)
WHERE status IN ('queued', 'waiting_approval', 'approved', 'running')
"""


def _loads(value, default):
    try:
        return json.loads(value or "")
    except json.JSONDecodeError:
        return default


def _row_to_action(row) -> dict[str, Any]:
    item = dict(row)
    item["requires_approval"] = bool(item["requires_approval"])
    item["approved"] = bool(item["approved"])
    item["payload"] = _loads(item.get("payload"), {})
    item["result"] = _loads(item.get("result"), {})
    return item


def _retire_duplicate_active_actions(conn) -> None:
    groups = conn.execute(
        f"""
        SELECT asset_id, action_type
        FROM actions
        WHERE status IN ({ACTIVE_STATUS_SQL})
        GROUP BY asset_id, action_type
        HAVING COUNT(*) > 1
        ORDER BY asset_id ASC, action_type ASC
        """
    ).fetchall()
    for group in groups:
        rows = conn.execute(
            f"""
            SELECT action_id, status, created_at, result
            FROM actions
            WHERE asset_id = ? AND action_type = ?
              AND status IN ({ACTIVE_STATUS_SQL})
            ORDER BY CASE status
                WHEN 'running' THEN 0
                WHEN 'approved' THEN 1
                WHEN 'waiting_approval' THEN 2
                WHEN 'queued' THEN 3
                ELSE 4
            END ASC, created_at ASC, action_id ASC
            """,
            (group["asset_id"], group["action_type"]),
        ).fetchall()
        survivor = rows[0]
        for duplicate in rows[1:]:
            previous_status = duplicate["status"]
            terminal_status = "failed" if previous_status == "running" else "cancelled"
            previous_result = _loads(duplicate["result"], {})
            if not isinstance(previous_result, dict):
                previous_result = {"previous_result": previous_result}
            previous_result["atomic_dedup_migration"] = {
                "retired": True,
                "survivor_action_id": survivor["action_id"],
                "previous_status": previous_status,
            }
            conn.execute(
                """
                UPDATE actions
                SET status = ?, updated_at = ?, explanation = ?, result = ?
                WHERE action_id = ?
                """,
                (
                    terminal_status,
                    now_iso(),
                    f"Retired by atomic Action Queue deduplication migration. Survivor action_id: {survivor['action_id']}. Previous status: {previous_status}.",
                    json.dumps(previous_result, sort_keys=True),
                    duplicate["action_id"],
                ),
            )


def initialize_action_tables() -> None:
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(ACTION_SCHEMA)
        _retire_duplicate_active_actions(conn)
        conn.execute(ACTIVE_ACTION_UNIQUE_INDEX)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _insert_action(conn, action: Action) -> dict[str, Any]:
    data = action.to_dict()
    if data["status"] not in ACTION_STATUSES:
        data["status"] = "waiting_approval"
    conn.execute(
        """
        INSERT INTO actions (action_id, created_at, updated_at, requested_by, source, asset_id, action_type, status, priority, requires_approval, approved, approved_by, approved_at, safety_status, reason, explanation, payload, result)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["action_id"], data["created_at"], data["updated_at"], data["requested_by"], data["source"], data["asset_id"], data["action_type"], data["status"],
            int(data["priority"]), 1 if data["requires_approval"] else 0, 1 if data["approved"] else 0, data.get("approved_by"), data.get("approved_at"),
            data["safety_status"], data["reason"], data["explanation"], json.dumps(data.get("payload", {}), sort_keys=True), json.dumps(data.get("result", {}), sort_keys=True),
        ),
    )
    return data


def insert_action(action: Action) -> dict[str, Any]:
    conn = connect()
    try:
        data = _insert_action(conn, action)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_action(data["action_id"])


def update_action(action_id: str, **changes: Any) -> dict[str, Any] | None:
    existing = get_action(action_id)
    if not existing:
        return None
    existing.update(changes)
    existing["updated_at"] = now_iso()
    conn = connect()
    conn.execute(
        """
        UPDATE actions SET updated_at = ?, requested_by = ?, source = ?, asset_id = ?, action_type = ?, status = ?, priority = ?, requires_approval = ?, approved = ?, approved_by = ?, approved_at = ?, safety_status = ?, reason = ?, explanation = ?, payload = ?, result = ? WHERE action_id = ?
        """,
        (
            existing["updated_at"], existing["requested_by"], existing["source"], existing["asset_id"], existing["action_type"], existing["status"], int(existing["priority"]),
            1 if existing["requires_approval"] else 0, 1 if existing["approved"] else 0, existing.get("approved_by"), existing.get("approved_at"), existing["safety_status"],
            existing["reason"], existing["explanation"], json.dumps(existing.get("payload", {}), sort_keys=True), json.dumps(existing.get("result", {}), sort_keys=True), action_id,
        ),
    )
    conn.commit()
    conn.close()
    return get_action(action_id)


def get_action(action_id: str) -> dict[str, Any] | None:
    conn = connect()
    row = conn.execute("SELECT * FROM actions WHERE action_id = ?", (action_id,)).fetchone()
    conn.close()
    return _row_to_action(row) if row else None


def list_actions(limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 1000))
    conn = connect()
    if status:
        rows = conn.execute("SELECT * FROM actions WHERE status = ? ORDER BY priority ASC, created_at DESC LIMIT ?", (status, safe_limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM actions ORDER BY created_at DESC LIMIT ?", (safe_limit,)).fetchall()
    conn.close()
    return [_row_to_action(row) for row in rows]
