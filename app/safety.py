from app import config
from app.assets.registry import asset_registry
from app.assets.relationships import list_dependency_requirements

FORBIDDEN_ACTIONS = {
    "delete_volume",
    "delete_container",
    "prune",
    "change_firewall",
    "change_dns",
    "exec_shell",
    "delete_file",
    "delete_docker_volume",
}


def can_restart_container(container_name, container_status):
    if not config.SAFE_MODE:
        return False, "SAFE_MODE er slået fra."
    if not config.ALLOW_RESTART_STOPPED:
        return False, "Start af stoppede containere er slået fra."
    if container_status != "exited":
        return False, "Kun stoppede containere må startes."
    if container_name in config.PROTECTED_CONTAINERS:
        return False, "Containeren er beskyttet."
    if config.ALLOWED_RESTART_CONTAINERS and container_name not in config.ALLOWED_RESTART_CONTAINERS:
        return False, "Containeren er ikke på manuel allow-list."
    return True, "Tilladt af safe mode regler."


def configured_dependencies_available(asset_id):
    for requirement in list_dependency_requirements(asset_id):
        dependency_id = requirement["target_asset_id"]
        required_state = requirement["required_state"]
        dependency = asset_registry.get_asset(dependency_id)
        if not dependency or dependency.get("state") != required_state:
            return False, f"Afhængighed {dependency_id} skal være {required_state}."
    return True, "Konfigurerede afhængigheder er tilgængelige."


def can_auto_start(container, containers, recent_failures):
    del containers
    name = container["name"]
    asset_id = container.get("asset_id") or f"docker:{name}"
    status = container.get("docker_state") or container.get("status")

    if not config.SAFE_MODE:
        return False, "SAFE_MODE er slået fra."
    if status != "exited":
        return False, "Containeren er ikke stoppet."
    if container.get("classification") != "optional":
        return False, "Kun optional services må auto-startes."
    if container.get("protected") or name in config.PROTECTED_CONTAINERS:
        return False, "Containeren er beskyttet."
    if not container.get("auto_start_allowed"):
        return False, "Containeren er ikke på auto-start allow-list."
    dependencies_ok, dependency_reason = configured_dependencies_available(asset_id)
    if not dependencies_ok:
        return False, dependency_reason
    if recent_failures >= config.AUTO_START_FAILURE_LIMIT:
        return False, "For mange fejl inden for fejlvinduet."
    return True, "Auto-start tilladt af safe mode regler."


def is_forbidden_action(action):
    return action in FORBIDDEN_ACTIONS
