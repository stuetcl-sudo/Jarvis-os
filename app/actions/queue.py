from app.actions.action import Action, now_iso
from app.actions.history import get_action, insert_action, list_actions, update_action


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
    status = "waiting_approval" if requires_approval else "queued"
    action = Action(
        requested_by=requested_by,
        source=source,
        asset_id=asset_id,
        action_type=action_type,
        reason=reason,
        requires_approval=requires_approval,
        priority=priority,
        payload=payload or {},
        status=status,
        approved=not requires_approval,
        approved_by=None if requires_approval else requested_by,
        approved_at=None if requires_approval else now_iso(),
        explanation="Action queued. It cannot run until safety checks pass and approval is present when required.",
    )
    return insert_action(action)


def approve_action(action_id: str, approved_by: str = "user") -> dict | None:
    action = get_action(action_id)
    if not action or action["status"] in {"completed", "failed", "denied", "cancelled"}:
        return action
    return update_action(
        action_id,
        status="approved",
        approved=True,
        approved_by=approved_by,
        approved_at=now_iso(),
        explanation="Action manually approved. It still requires safety checks before execution.",
    )


def deny_action(action_id: str, denied_by: str = "user") -> dict | None:
    action = get_action(action_id)
    if not action or action["status"] in {"completed", "failed", "denied", "cancelled"}:
        return action
    return update_action(action_id, status="denied", safety_status="denied", explanation=f"Action denied by {denied_by}.", result={"denied_by": denied_by})


def cancel_action(action_id: str, cancelled_by: str = "user") -> dict | None:
    action = get_action(action_id)
    if not action or action["status"] in {"completed", "failed", "denied", "cancelled"}:
        return action
    return update_action(action_id, status="cancelled", explanation=f"Action cancelled by {cancelled_by}.", result={"cancelled_by": cancelled_by})


__all__ = ["queue_action", "approve_action", "deny_action", "cancel_action", "get_action", "list_actions", "update_action"]
