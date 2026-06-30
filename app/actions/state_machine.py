from dataclasses import dataclass
from typing import Any

from app.actions.action import now_iso
from app.actions.history import get_action
from app.db import connect

TERMINAL_STATUSES = {"completed", "failed", "denied", "cancelled"}
ALLOWED_TRANSITIONS = {
    "waiting_approval": {"approved", "denied", "cancelled"},
    "approved": {"running", "denied", "cancelled"},
    "running": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
    "denied": set(),
    "cancelled": set(),
}


class ActionTransitionConflict(Exception):
    pass


@dataclass(frozen=True)
class TransitionResult:
    action: dict[str, Any] | None
    changed: bool
    reason: str | None = None


def validate_transition(current_status: str, target_status: str) -> None:
    if current_status == target_status:
        raise ActionTransitionConflict(f"Action is already {target_status}.")
    if current_status in TERMINAL_STATUSES:
        raise ActionTransitionConflict(f"Terminal action cannot transition from {current_status} to {target_status}.")
    if target_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
        raise ActionTransitionConflict(f"Invalid action transition from {current_status} to {target_status}.")


def transition_action(action_id: str, target_status: str, **changes: Any) -> TransitionResult:
    current = get_action(action_id)
    if not current:
        return TransitionResult(None, False, None)
    validate_transition(current["status"], target_status)
    expected_status = current["status"]
    updated = {**current, **changes, "status": target_status, "updated_at": now_iso()}
    conn = connect()
    cur = conn.execute(
        """
        UPDATE actions
        SET updated_at = ?, status = ?, approved = ?, approved_by = ?, approved_at = ?, safety_status = ?, explanation = ?, result = ?
        WHERE action_id = ? AND status = ?
        """,
        (
            updated["updated_at"],
            updated["status"],
            1 if updated.get("approved") else 0,
            updated.get("approved_by"),
            updated.get("approved_at"),
            updated.get("safety_status", current.get("safety_status")),
            updated.get("explanation", current.get("explanation")),
            __import__("json").dumps(updated.get("result", current.get("result", {})), sort_keys=True),
            action_id,
            expected_status,
        ),
    )
    conn.commit()
    conn.close()
    if cur.rowcount != 1:
        latest = get_action(action_id)
        return TransitionResult(latest, False, "Action status changed before transition could be applied.")
    return TransitionResult(get_action(action_id), True, None)


def claim_approved_action(action_id: str) -> TransitionResult:
    now = now_iso()
    conn = connect()
    cur = conn.execute(
        "UPDATE actions SET status = 'running', updated_at = ?, safety_status = 'passed', explanation = 'Action claimed for execution.' WHERE action_id = ? AND status = 'approved' AND approved = 1",
        (now, action_id),
    )
    conn.commit()
    conn.close()
    if cur.rowcount != 1:
        current = get_action(action_id)
        if not current:
            return TransitionResult(None, False, None)
        return TransitionResult(current, False, f"Action could not be claimed from status {current['status']}.")
    return TransitionResult(get_action(action_id), True, None)
