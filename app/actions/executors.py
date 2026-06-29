import docker
from docker.errors import DockerException, NotFound

from app.actions.verification import verify_docker_state
from app.brain import add_recommendation
from app.db import create_incident
from app.events.dispatcher import publish


def execute_docker_start(action: dict) -> tuple[bool, dict, str]:
    asset_id = action["asset_id"]
    name = asset_id.split(":", 1)[1] if ":" in asset_id else asset_id
    try:
        client = docker.from_env()
        container = client.containers.get(name)
        container.reload()
        inspected = client.api.inspect_container(container.id)
        state = inspected.get("State", {}).get("Status")
        if state != "exited":
            return False, {"before_state": state}, f"Container must be exited before start. Current state is {state}."
        container.start()
        ok, verify_reason, live = verify_docker_state(asset_id, "running")
        if ok:
            publish("action_engine", "Action.Completed", "info", asset_id, {"asset_id": asset_id, "action_id": action["action_id"], "action_type": action["action_type"], "verified": True}, asset_id=asset_id)
            return True, {"before_state": state, "after": live, "verified": True}, verify_reason
        publish("action_engine", "Action.Failed", "warning", asset_id, {"asset_id": asset_id, "action_id": action["action_id"], "action_type": action["action_type"], "verified": False, "reason": verify_reason}, asset_id=asset_id)
        return False, {"before_state": state, "after": live, "verified": False}, verify_reason
    except NotFound:
        return False, {}, "Container not found."
    except DockerException as exc:
        return False, {}, str(exc)


def execute_recommendation_create(action: dict) -> tuple[bool, dict, str]:
    payload = action.get("payload", {}) or {}
    add_recommendation(payload.get("severity", "info"), "action", action.get("asset_id"), payload.get("title", "Action recommendation"), payload.get("detail", action.get("reason", "Recommendation created by Action Engine.")))
    publish("action_engine", "Action.Completed", "info", action.get("asset_id"), {"asset_id": action.get("asset_id"), "action_id": action["action_id"], "action_type": action["action_type"]}, asset_id=action.get("asset_id"))
    return True, {"created": "recommendation"}, "Recommendation created."


def execute_incident_create(action: dict) -> tuple[bool, dict, str]:
    payload = action.get("payload", {}) or {}
    create_incident(payload.get("severity", "warning"), action.get("asset_id"), payload.get("title", "Action incident"), payload.get("detail", action.get("reason", "Incident created by Action Engine.")))
    publish("action_engine", "Action.Completed", "info", action.get("asset_id"), {"asset_id": action.get("asset_id"), "action_id": action["action_id"], "action_type": action["action_type"]}, asset_id=action.get("asset_id"))
    return True, {"created": "incident"}, "Incident created."


def execute_notification_stub(action: dict) -> tuple[bool, dict, str]:
    publish("action_engine", "Notification.StubCreated", "info", action.get("asset_id"), {"asset_id": action.get("asset_id"), "action_id": action["action_id"], "message": action.get("reason")}, asset_id=action.get("asset_id"))
    return True, {"stub": True}, "Notification stub created."


def execute_action(action: dict) -> tuple[bool, dict, str]:
    action_type = action.get("action_type")
    if action_type == "docker.start_container":
        return execute_docker_start(action)
    if action_type == "recommendation.create":
        return execute_recommendation_create(action)
    if action_type == "incident.create":
        return execute_incident_create(action)
    if action_type == "notification.create_stub":
        return execute_notification_stub(action)
    return False, {}, f"No executor exists for {action_type}."
