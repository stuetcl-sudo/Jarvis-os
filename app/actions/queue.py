from app.actions.action import Action, now_iso
from app.actions.history import get_action, insert_action, list_actions
from app.actions.state_machine import transition_action

ACTIVE_STATUSES = {"queued", "waiting_approval", "approved", "running"}


def with_dedup_flag(action: dict, deduplicated: bool) -> dict:
    return {**action, "deduplicated": deduplicated}


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
        return with_dedup_flag(existing, True)
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
    return with_dedup_flag(insert_action(action), False)


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
