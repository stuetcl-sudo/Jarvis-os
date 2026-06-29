from app import config

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


def can_auto_start(container, containers, recent_failures):
    name = container["name"]
    status = container.get("docker_state") or container.get("status")

    if not config.SAFE_MODE:
        return False, "SAFE_MODE er slået fra."
    if status != "exited":
        return False, "Containeren er ikke stoppet."
    if container.get("classification") != "optional":
        return False, "Kun optional services må auto-startes."
    if container.get("protected") or name in config.PROTECTED_CONTAINERS:
        return False, "Containeren er beskyttet."
    if name == "gluetun":
        return False, "Gluetun må aldrig auto-startes."
    if name.lower() == "qbittorrent":
        gluetun = next((c for c in containers if c["name"].lower() == "gluetun"), None)
        if not gluetun or (gluetun.get("docker_state") or gluetun.get("status")) != "running":
            return False, "qBittorrent må kun startes når gluetun kører."
    if not container.get("auto_start_allowed"):
        return False, "Containeren er ikke på auto-start allow-list."
    if recent_failures >= config.AUTO_START_FAILURE_LIMIT:
        return False, "For mange fejl inden for fejlvinduet."
    return True, "Auto-start tilladt af safe mode regler."


def is_forbidden_action(action):
    return action in FORBIDDEN_ACTIONS
