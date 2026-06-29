import docker
from docker.errors import DockerException, NotFound

from app import config


def client():
    return docker.from_env()


def list_containers():
    items = []
    try:
        for container in client().containers.list(all=True):
            attrs = container.attrs
            state = attrs.get("State", {})
            items.append(
                {
                    "id": container.short_id,
                    "name": container.name,
                    "image": attrs.get("Config", {}).get("Image", "unknown"),
                    "status": container.status,
                    "created": attrs.get("Created"),
                    "restart_count": state.get("RestartCount", 0),
                    "protected": container.name in config.PROTECTED_CONTAINERS,
                }
            )
        return items, None
    except DockerException as exc:
        return [], str(exc)


def restart_container(name):
    try:
        c = client().containers.get(name)
        c.start()
        return True, "Container started."
    except NotFound:
        return False, "Container not found."
    except DockerException as exc:
        return False, str(exc)
