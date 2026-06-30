import sqlite3

from app.actions.action import Action, now_iso
from app.actions.history import _insert_action, _row_to_action, get_action, list_actions
from app.actions.state_machine import transition_action
from app.db import connect

ACTIVE_STATUS_SQL = "'queued', 'waiting_approval', 'approved', 'running'"


def with_dedup_flag(action: dict, deduplicated: bool) -> dict:
    return {**action, "deduplicated": deduplicated}


def _find_active_row(conn, asset_id: str, action_type: str):
    return conn.execute(
        f"""
        SELECT * FROM actions
        WHERE asset_id = ? AND action_type = ?
          AND status IN ({ACTIVE_STATUS_SQL})
        ORDER BY CASE status
            WHEN 'running' THEN 0
            WHEN 'approved' THEN 1
            WHEN 'waiting_approval' THEN 2
            WHEN 'queued' THEN 3
            ELSE 4
        END ASC, created_at ASC, action_id ASC
        LIMIT 1
        """,
        (asset_id, action_type),
    ).fetchone()


def find_active_action(asset_id: str, action_type: str) -> dict | None:
    conn = connect()
    try:
        row = _find_active_row(conn, asset_id, action_type)
        return _row_to_action(row) if row else None
    finally:
        conn.close()


def queue_action(
    asset_id: str,
    action_type: str,
    requested_by: str = "user",
    source: str = "manual",
    reason: str = "manual action request",
    requires_approval: bool = True,
    priority: int = 100,
    payload: dict | None = None,
) -> dict:
    forced_approval = True if action_type == "docker.start_container" or source != "trusted_internal" else bool(requires_approval)
    status = "waiting_approval" if forced_approval else "queued"
    action = Action(
        requested_by=requested_by,
        source=source,
        asset_id=asset_id,
        action_type=action_type,
        reason=reason,
        requires_approval=forced_approval,
        priority=priority,
        payload=payload or {},
        status=status,
        approved=False,
        approved_by=None,
        approved_at=None,
        explanation="Action queued. It cannot run until safety checks pass and approval is present when required.",
    )
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = _find_active_row(conn, asset_id, action_type)
        if existing:
            result = with_dedup_flag(_row_to_action(existing), True)
            conn.commit()
            return result
        data = _insert_action(conn, action)
        conn.commit()
        return with_dedup_flag(data, False)
    except sqlite3.IntegrityError:
        conn.rollback()
        winner = find_active_action(asset_id, action_type)
        if winner:
            return with_dedup_flag(winner, True)
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def approve_action(action_id: str, approved_by: str = "user"):
    return transition_action(
        action_id,
        "approved",
        approved=True,
        approved_by=approved_by,
        approved_at=now_iso(),
        explanation="Action manually approved. It still requires safety checks before execution.",
    )


def deny_action(action_id: str, denied_by: str = "user"):
    return transition_action(action_id, "denied", safety_status="denied", explanation=f"Action denied by {denied_by}.", result={"denied_by": denied_by})


def cancel_action(action_id: str, cancelled_by: str = "user"):
    return transition_action(action_id, "cancelled", explanation=f"Action cancelled by {cancelled_by}.", result={"cancelled_by": cancelled_by})


__all__ = ["queue_action", "approve_action", "deny_action", "cancel_action", "get_action", "list_actions", "find_active_action"]
