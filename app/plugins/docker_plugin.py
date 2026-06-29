from typing import Any

import docker
from docker.errors import DockerException, NotFound

from app import config
from app.events.types import EventTypes
from app.plugins.base import PluginBase


class DockerPlugin(PluginBase):
    name = "docker"
    description = "Event-aware Docker container inventory plugin"

    def client(self):
        return docker.from_env()

    def classify(self, name: str) -> str:
        if name in config.IGNORED_SERVICES:
            return "stopped_by_design"
        if name in config.CRITICAL_SERVICES:
            return "critical"
        if name in config.OPTIONAL_SERVICES:
            return "optional"
        return "unknown"

    def list_containers(self):
        items = []
        try:
            for container in self.client().containers.list(all=True):
                attrs = container.attrs
                state = attrs.get("State", {})
                name = container.name
                classification = self.classify(name)
                item = {
                    "id": container.short_id,
                    "name": name,
                    "image": attrs.get("Config", {}).get("Image", "unknown"),
                    "status": container.status,
                    "created": attrs.get("Created"),
                    "restart_count": state.get("RestartCount", 0),
                    "protected": name in config.PROTECTED_CONTAINERS,
                    "classification": classification,
                    "auto_start_allowed": name in config.ALLOWED_AUTO_START_CONTAINERS,
                }
                items.append(item)
            items = sorted(items, key=lambda c: c["name"])
            self.publish(EventTypes.DOCKER_COLLECTED, "info", "docker", {"total": len(items)})
            for item in items:
                if item["status"] == "exited":
                    severity = "critical" if item["classification"] == "critical" else "warning"
                    self.publish(EventTypes.CONTAINER_STOPPED, severity, item["name"], item)
                elif item["status"] == "running":
                    self.publish(EventTypes.CONTAINER_STARTED, "info", item["name"], item)
                if item["classification"] == "unknown":
                    self.publish(EventTypes.CONTAINER_UNKNOWN, "info", item["name"], item)
            return items, None
        except DockerException as exc:
            return [], str(exc)

    def start_container(self, name: str):
        try:
            container = self.client().containers.get(name)
            container.start()
            self.publish(EventTypes.CONTAINER_STARTED, "info", name, {"reason": "manual_or_safe_auto_start"})
            return True, "Container started."
        except NotFound:
            return False, "Container not found."
        except DockerException as exc:
            return False, str(exc)

    def collect(self) -> dict[str, Any]:
        containers, error = self.list_containers()
        return {"plugin": self.name, "error": error, "containers": containers}
