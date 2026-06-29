from app import config
from app.assets.registry import asset_registry
from app.assets.relationships import list_relationships
from app.policies.engine import policy_engine

ALLOWED_ACTION_TYPES = {
    "docker.start_container",
    "recommendation.create",
    "incident.create",
    "notification.create_stub",
}
DESTRUCTIVE_ACTION_TYPES = {
    "docker.stop_container",
    "docker.delete_container",
    "docker.prune",
    "docker.exec",
    "docker.compose",
    "file.delete",
    "firewall.change",
    "dns.change",
    "volume.delete",
}


def _policy_decision_allows(action: dict, asset: dict) -> tuple[bool, str]:
    payload = action.get("payload", {}) or {}
    decision_id = payload.get("policy_decision_id")
    if action.get("source") != "policy":
        return True, "Manual/user action does not require a policy decision id, but still requires approval and safety checks."
    if not decision_id:
        return False, "Policy-sourced actions require an allowed policy decision id."
    for decision in policy_engine.list_decisions(500):
        if decision.get("decision_id") == decision_id:
            if decision.get("allowed"):
                return True, "Referenced policy decision allows this queued action."
            return False, "Referenced policy decision denied this action."
    return False, "Policy decision id was not found."


def _dependency_guards_pass(action: dict, asset: dict) -> tuple[bool, str]:
    if action.get("asset_id") == "docker:qbittorrent":
        gluetun = asset_registry.get_asset("docker:gluetun")
        if not gluetun or gluetun.get("state") != "running":
            return False, "Dependency guard denied action: docker:gluetun must be running before qBittorrent can be started."
    for rel in list_relationships(asset_id=action.get("asset_id"), relationship_type="depends_on"):
        target = asset_registry.get_asset(rel.get("target_asset_id"))
        if rel.get("target_asset_id") == "docker:gluetun" and (not target or target.get("state") != "running"):
            return False, "Dependency guard denied action: docker:gluetun must be running."
    return True, "Dependency guards passed."


def check_action_safety(action: dict) -> tuple[bool, str, str]:
    action_type = action.get("action_type")
    asset_id = action.get("asset_id")
    if not config.SAFE_MODE:
        return False, "denied", "SAFE_MODE must be true before any action can run."
    if action_type in DESTRUCTIVE_ACTION_TYPES:
        return False, "denied", f"Action type {action_type} is destructive and forbidden."
    if action_type not in ALLOWED_ACTION_TYPES:
        return False, "denied", f"Action type {action_type} is not in the allowed v0.7 action list."

    asset = asset_registry.get_asset(asset_id)
    if not asset:
        return False, "denied", f"Asset {asset_id} does not exist."
    if asset.get("classification") == "unknown":
        return False, "denied", "Unknown assets must never receive automatic or queued restart actions."
    if asset.get("protected") and action_type == "docker.start_container":
        return False, "denied", "Protected assets cannot receive restart/start actions."

    policy_ok, policy_reason = _policy_decision_allows(action, asset)
    if not policy_ok:
        return False, "denied", policy_reason

    if action_type == "docker.start_container":
        if asset.get("asset_type") != "docker_container":
            return False, "denied", "docker.start_container only supports docker_container assets."
        if asset.get("state") != "exited":
            return False, "denied", f"Docker asset must be exited before start. Current state is {asset.get('state')}."
        if asset.get("classification") != "optional":
            return False, "denied", "Only optional Docker assets can be started by the Action Engine."
        if not asset.get("auto_actions_allowed") and not action.get("approved"):
            return False, "waiting_approval", "Manual approval is required because auto_actions_allowed is false."
        dep_ok, dep_reason = _dependency_guards_pass(action, asset)
        if not dep_ok:
            return False, "denied", dep_reason
        return True, "passed", f"Safety passed. {policy_reason} {dep_reason}"

    return True, "passed", f"Safe non-destructive action approved. {policy_reason}"
