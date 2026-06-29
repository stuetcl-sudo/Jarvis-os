import docker
from docker.errors import DockerException, NotFound

from app import config


def client():
    return docker.from_env()


def classify(name):
    if name in config.IGNORED_SERVICES:
        return "stopped_by_design"
    if name in config.CRITICAL_SERVICES:
        return "critical"
    if name in config.OPTIONAL_SERVICES:
        return "optional"
    return "unknown"


def list_containers():
    items = []
    try:
        for container in client().containers.list(all=True):
            attrs = container.attrs
            state = attrs.get("State", {})
            name = container.name
            items.append(
                {
                    "id": container.short_id,
                    "name": name,
                    "image": attrs.get("Config", {}).get("Image", "unknown"),
                    "status": container.status,
                    "created": attrs.get("Created"),
                    "restart_count": state.get("RestartCount", 0),
                    "protected": name in config.PROTECTED_CONTAINERS,
                    "classification": classify(name),
                    "auto_start_allowed": name in config.ALLOWED_AUTO_START_CONTAINERS,
                }
            )
        return sorted(items, key=lambda c: c["name"]), None
    except DockerException as exc:
        return [], str(exc)


def start_container(name):
    try:
        c = client().containers.get(name)
        c.start()
        return True, "Container started."
    except NotFound:
        return False, "Container not found."
    except DockerException as exc:
        return False, str(exc)


restart_container = start_container
