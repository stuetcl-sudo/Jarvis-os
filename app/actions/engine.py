from app.actions.executors import execute_action
from app.actions.history import get_action, initialize_action_tables, list_actions
from app.actions.queue import approve_action, cancel_action, deny_action, queue_action
from app.actions.safety import check_action_safety
from app.actions.state_machine import ActionTransitionConflict, claim_approved_action, transition_action
from app.events.dispatcher import publish


class ActionConflict(Exception):
    pass


class ActionEngine:
    def initialize(self) -> None:
        initialize_action_tables()

    def queue_action(self, **kwargs):
        action = queue_action(**kwargs)
        publish("action_engine", "Action.Queued", "info", action["asset_id"], {"asset_id": action["asset_id"], "action_id": action["action_id"], "action_type": action["action_type"], "status": action["status"]}, asset_id=action["asset_id"])
        return action

    def approve_action(self, action_id: str, approved_by: str = "user"):
        result = approve_action(action_id, approved_by)
        if result.changed and result.action:
            publish("action_engine", "Action.Approved", "info", result.action["asset_id"], {"asset_id": result.action["asset_id"], "action_id": action_id}, asset_id=result.action["asset_id"])
        if result.reason:
            raise ActionConflict(result.reason)
        return result.action

    def deny_action(self, action_id: str, denied_by: str = "user"):
        result = deny_action(action_id, denied_by)
        if result.changed and result.action:
            publish("action_engine", "Action.Denied", "warning", result.action["asset_id"], {"asset_id": result.action["asset_id"], "action_id": action_id}, asset_id=result.action["asset_id"])
        if result.reason:
            raise ActionConflict(result.reason)
        return result.action

    def cancel_action(self, action_id: str, cancelled_by: str = "user"):
        result = cancel_action(action_id, cancelled_by)
        if result.changed and result.action:
            publish("action_engine", "Action.Cancelled", "info", result.action["asset_id"], {"asset_id": result.action["asset_id"], "action_id": action_id}, asset_id=result.action["asset_id"])
        if result.reason:
            raise ActionConflict(result.reason)
        return result.action

    def get_action(self, action_id: str):
        return get_action(action_id)

    def list_actions(self, limit: int = 100, status: str | None = None):
        return list_actions(limit, status)

    def run_action(self, action_id: str):
        current = get_action(action_id)
        if not current:
            return None
        if current["status"] != "approved" or not current["approved"]:
            raise ActionConflict(f"Action must be approved before run. Current status is {current['status']}.")
        allowed, safety_status, reason = check_action_safety(current)
        if not allowed:
            target = "denied" if safety_status == "denied" else "cancelled"
            result = transition_action(current["action_id"], target, safety_status=safety_status, explanation=reason, result={"safety": reason})
            if result.changed and result.action:
                publish("action_engine", "Action.Denied", "warning", result.action["asset_id"], {"asset_id": result.action["asset_id"], "action_id": action_id, "reason": reason}, asset_id=result.action["asset_id"])
            return result.action
        claimed = claim_approved_action(action_id)
        if not claimed.changed:
            raise ActionConflict(claimed.reason or "Action could not be claimed for execution.")
        running = claimed.action
        publish("action_engine", "Action.Running", "info", running["asset_id"], {"asset_id": running["asset_id"], "action_id": action_id, "action_type": running["action_type"]}, asset_id=running["asset_id"])
        try:
            ok, exec_result, exec_reason = execute_action(running)
            status = "completed" if ok else "failed"
            finished = transition_action(action_id, status, result=exec_result, explanation=f"{reason} Execution: {exec_reason}")
            if not ok and finished.action:
                publish("action_engine", "Action.Failed", "error", finished.action["asset_id"], {"asset_id": finished.action["asset_id"], "action_id": action_id, "reason": exec_reason}, asset_id=finished.action["asset_id"])
            return finished.action
        except Exception as exc:
            failed = transition_action(action_id, "failed", result={"error": str(exc)}, explanation=f"{reason} Execution raised an exception: {exc}")
            if failed.action:
                publish("action_engine", "Action.Failed", "error", failed.action["asset_id"], {"asset_id": failed.action["asset_id"], "action_id": action_id, "reason": str(exc)}, asset_id=failed.action["asset_id"])
            return failed.action


action_engine = ActionEngine()
