from app.actions.action import Action, now_iso
from app.actions.history import get_action, insert_action, list_actions, update_action

ACTIVE_STATUSES = {"queued", "waiting_approval", "approved", "running"}
TERMINAL_STATUSES = {"completed", "failed", "denied", "cancelled"}


def find_active_action(asset_id: str, action_type: str) -> dict | None:
    for action in list_actions(1000):
        if action["asset_id"] == asset_id and action["action_type"] == action_type and action["status"] in ACTIVE_STATUSES:
            return action
    return None


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
    existing = find_active_action(asset_id, action_type)
    if existing:
        return existing
    manual_source = source not in {"trusted_internal"}
    forced_approval = True if manual_source or action_type == "docker.start_container" else bool(requires_approval)
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
    return insert_action(action)


def approve_action(action_id: str, approved_by: str = "user") -> tuple[dict | None, bool, str | None]:
    action = get_action(action_id)
    if not action:
        return None, False, None
    if action["status"] != "waiting_approval":
        return action, False, f"Cannot approve action in status {action['status']}."
    return update_action(
        action_id,
        status="approved",
        approved=True,
        approved_by=approved_by,
        approved_at=now_iso(),
        explanation="Action manually approved. It still requires safety checks before execution.",
    ), True, None


def deny_action(action_id: str, denied_by: str = "user") -> tuple[dict | None, bool, str | None]:
    action = get_action(action_id)
    if not action:
        return None, False, None
    if action["status"] not in {"queued", "waiting_approval", "approved"}:
        return action, False, f"Cannot deny action in status {action['status']}."
    return update_action(action_id, status="denied", safety_status="denied", explanation=f"Action denied by {denied_by}.", result={"denied_by": denied_by}), True, None


def cancel_action(action_id: str, cancelled_by: str = "user") -> tuple[dict | None, bool, str | None]:
    action = get_action(action_id)
    if not action:
        return None, False, None
    if action["status"] not in {"queued", "waiting_approval", "approved"}:
        return action, False, f"Cannot cancel action in status {action['status']}."
    return update_action(action_id, status="cancelled", explanation=f"Action cancelled by {cancelled_by}.", result={"cancelled_by": cancelled_by}), True, None


__all__ = ["queue_action", "approve_action", "deny_action", "cancel_action", "get_action", "list_actions", "update_action", "find_active_action"]
