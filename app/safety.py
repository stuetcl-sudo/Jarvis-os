from app import config

FORBIDDEN_ACTIONS = {
    "delete_volume",
    "delete_container",
    "prune",
    "change_firewall",
    "change_dns",
    "exec_shell",
}


def can_restart_container(container_name, container_status):
    if not config.SAFE_MODE:
        return False, "SAFE_MODE is disabled; v0.1 refuses automated restarts outside safe mode."
    if not config.ALLOW_RESTART_STOPPED:
        return False, "Restarting stopped containers is disabled."
    if container_status != "exited":
        return False, "Only stopped containers may be restarted by v0.1."
    if container_name in config.PROTECTED_CONTAINERS:
        return False, "Container is protected."
    if config.ALLOWED_RESTART_CONTAINERS and container_name not in config.ALLOWED_RESTART_CONTAINERS:
        return False, "Container is not in ALLOWED_RESTART_CONTAINERS."
    return True, "Allowed by v0.1 safe mode rules."


def is_forbidden_action(action):
    return action in FORBIDDEN_ACTIONS
