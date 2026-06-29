from app.actions.executors import execute_action
from app.actions.history import get_action, initialize_action_tables, list_actions, update_action
from app.actions.queue import approve_action, cancel_action, deny_action, queue_action
from app.actions.safety import check_action_safety
from app.events.dispatcher import publish


class ActionEngine:
    def initialize(self) -> None:
        initialize_action_tables()

    def queue_action(self, **kwargs):
        action = queue_action(**kwargs)
        publish("action_engine", "Action.Queued", "info", action["asset_id"], {"asset_id": action["asset_id"], "action_id": action["action_id"], "action_type": action["action_type"], "status": action["status"]}, asset_id=action["asset_id"])
        return action

    def approve_action(self, action_id: str, approved_by: str = "user"):
        action = approve_action(action_id, approved_by)
        if action:
            publish("action_engine", "Action.Approved", "info", action["asset_id"], {"asset_id": action["asset_id"], "action_id": action_id}, asset_id=action["asset_id"])
        return action

    def deny_action(self, action_id: str, denied_by: str = "user"):
        action = deny_action(action_id, denied_by)
        if action:
            publish("action_engine", "Action.Denied", "warning", action["asset_id"], {"asset_id": action["asset_id"], "action_id": action_id}, asset_id=action["asset_id"])
        return action

    def cancel_action(self, action_id: str, cancelled_by: str = "user"):
        action = cancel_action(action_id, cancelled_by)
        if action:
            publish("action_engine", "Action.Cancelled", "info", action["asset_id"], {"asset_id": action["asset_id"], "action_id": action_id}, asset_id=action["asset_id"])
        return action

    def get_action(self, action_id: str):
        return get_action(action_id)

    def list_actions(self, limit: int = 100, status: str | None = None):
        return list_actions(limit, status)

    def run_action(self, action_id: str):
        action = get_action(action_id)
        if not action:
            return None
        if action["status"] in {"completed", "failed", "denied", "cancelled"}:
            return action
        if action["requires_approval"] and not action["approved"]:
            return update_action(action_id, status="waiting_approval", safety_status="waiting_approval", explanation="Manual approval is required before safety check and execution.")

        allowed, safety_status, reason = check_action_safety(action)
        if not allowed:
            updated = update_action(action_id, status="denied" if safety_status == "denied" else "waiting_approval", safety_status=safety_status, explanation=reason, result={"safety": reason})
            publish("action_engine", "Action.Denied", "warning", action["asset_id"], {"asset_id": action["asset_id"], "action_id": action_id, "reason": reason}, asset_id=action["asset_id"])
            return updated

        running = update_action(action_id, status="running", safety_status="passed", explanation=reason)
        publish("action_engine", "Action.Running", "info", action["asset_id"], {"asset_id": action["asset_id"], "action_id": action_id, "action_type": action["action_type"]}, asset_id=action["asset_id"])
        ok, result, exec_reason = execute_action(running)
        status = "completed" if ok else "failed"
        updated = update_action(action_id, status=status, result=result, explanation=f"{reason} Execution: {exec_reason}")
        if not ok:
            publish("action_engine", "Action.Failed", "error", action["asset_id"], {"asset_id": action["asset_id"], "action_id": action_id, "reason": exec_reason}, asset_id=action["asset_id"])
        return updated


action_engine = ActionEngine()
