from datetime import datetime, timezone
from typing import Any

import docker
from docker.errors import DockerException, NotFound

from app import config
from app.db import get_service_classification
from app.events.types import EventTypes
from app.plugins.base import PluginBase

VALID_DOCKER_STATES = {"running", "exited", "created", "restarting", "paused", "dead"}


class DockerPlugin(PluginBase):
    name = "docker"
    description = "Event-aware Docker container inventory plugin"

    def client(self):
        return docker.from_env()

    def classify(self, name: str) -> tuple[str, bool, bool]:
        saved = get_service_classification(name)
        config_protected = name in config.PROTECTED_CONTAINERS
        if saved:
            classification = saved["classification"]
            protected = bool(saved["protected"]) or config_protected
            allowed = bool(saved["auto_start_allowed"])
        elif name in config.IGNORED_SERVICES:
            classification, protected, allowed = "stopped_by_design", config_protected, False
        elif name in config.CRITICAL_SERVICES:
            classification, protected, allowed = "critical", config_protected, False
        elif name in config.OPTIONAL_SERVICES:
            classification, protected, allowed = "optional", config_protected, name in config.ALLOWED_AUTO_START_CONTAINERS
        else:
            classification, protected, allowed = "unknown", config_protected, False
        if classification != "optional" or protected:
            allowed = False
        return classification, protected, allowed

    def list_containers(self):
        items = []
        docker_read_at = datetime.now(timezone.utc).isoformat()
        try:
            api_client = self.client()
            for container in api_client.containers.list(all=True):
                container.reload()
                inspected = api_client.api.inspect_container(container.id)
                state = inspected.get("State", {})
                name = inspected.get("Name", container.name).lstrip("/")
                classification, protected, allowed = self.classify(name)
                docker_state = state.get("Status") or "unknown"
                if docker_state not in VALID_DOCKER_STATES:
                    docker_state = docker_state or "unknown"
                health_status = None
                if isinstance(state.get("Health"), dict):
                    health_status = state["Health"].get("Status")
                item = {
                    "id": container.short_id,
                    "name": name,
                    "image": inspected.get("Config", {}).get("Image", "unknown"),
                    "status": docker_state,
                    "docker_state": docker_state,
                    "docker_status": container.status,
                    "health_status": health_status,
                    "read_at": docker_read_at,
                    "created": inspected.get("Created"),
                    "restart_count": state.get("RestartCount", 0),
                    "protected": protected,
                    "classification": classification,
                    "auto_start_allowed": allowed,
                }
                items.append(item)
            items = sorted(items, key=lambda c: c["name"])
            self.publish(EventTypes.DOCKER_COLLECTED, "info", "docker", {"total": len(items), "docker_read_at": docker_read_at})
            for item in items:
                if item["docker_state"] == "exited":
                    severity = "critical" if item["classification"] == "critical" else "warning"
                    self.publish(EventTypes.CONTAINER_STOPPED, severity, item["name"], item)
                elif item["docker_state"] == "running":
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
