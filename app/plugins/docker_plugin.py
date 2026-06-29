from datetime import datetime, timezone
from typing import Any

import docker
from docker.errors import DockerException

from app import config
from app.assets.asset import Asset
from app.assets.registry import asset_registry
from app.assets.relationships import add_relationship
from app.assets.types import AssetTypes, RelationshipTypes
from app.db import get_service_classification
from app.events.types import EventTypes
from app.plugins.base import PluginBase

VALID_DOCKER_STATES = {"running", "exited", "created", "restarting", "paused", "dead"}
DOCKER_HOST_ASSET_ID = "system:docker"


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

    def register_docker_host_asset(self):
        asset_registry.register_asset(
            Asset(
                asset_id=DOCKER_HOST_ASSET_ID,
                asset_type=AssetTypes.SYSTEM_RESOURCE,
                plugin="system",
                name="docker",
                display_name="Docker Engine",
                state="observed",
                health=None,
                classification="critical",
                protected=True,
                auto_actions_allowed=False,
                metadata={"source": "docker_plugin"},
            )
        )

    def register_configured_dependencies(self):
        for source_asset_id, target_asset_id in config.ASSET_DEPENDENCIES:
            add_relationship(source_asset_id, RelationshipTypes.DEPENDS_ON, target_asset_id)

    def register_container_asset(self, item):
        asset_id = f"docker:{item['name']}"
        item["asset_id"] = asset_id
        asset_registry.register_asset(
            Asset(
                asset_id=asset_id,
                asset_type=AssetTypes.DOCKER_CONTAINER,
                plugin="docker",
                name=item["name"],
                display_name=item["name"],
                state=item["docker_state"],
                health=item.get("health_status"),
                classification=item["classification"],
                protected=item["protected"],
                auto_actions_allowed=item["auto_start_allowed"],
                metadata={
                    "container_id": item["id"],
                    "image": item["image"],
                    "docker_status": item.get("docker_status"),
                    "read_at": item.get("read_at"),
                    "restart_count": item.get("restart_count", 0),
                },
            )
        )
        add_relationship(DOCKER_HOST_ASSET_ID, RelationshipTypes.CONTAINS, asset_id)

    def transition_events_for(self, previous_asset, item):
        events = []
        payload = {**item, "asset_id": item["asset_id"]}
        previous_state = previous_asset.get("state") if previous_asset else None
        previous_classification = previous_asset.get("classification") if previous_asset else None
        current_state = item["docker_state"]
        current_classification = item["classification"]

        if previous_asset is None:
            events.append((EventTypes.CONTAINER_DISCOVERED, "info", payload))
            if current_classification == "unknown":
                events.append((EventTypes.CONTAINER_UNKNOWN, "info", payload))
            return events

        if previous_state != current_state:
            if previous_state == "running" and current_state == "exited":
                severity = "critical" if current_classification == "critical" else "warning"
                events.append((EventTypes.CONTAINER_STOPPED, severity, payload))
            elif previous_state == "exited" and current_state == "running":
                events.append((EventTypes.CONTAINER_STARTED, "info", payload))

        if previous_classification != "unknown" and current_classification == "unknown":
            events.append((EventTypes.CONTAINER_UNKNOWN, "info", payload))

        return events

    def list_containers(self):
        items = []
        pending_events = []
        docker_read_at = datetime.now(timezone.utc).isoformat()
        try:
            api_client = self.client()
            self.register_docker_host_asset()
            self.register_configured_dependencies()
            for container in api_client.containers.list(all=True):
                container.reload()
                inspected = api_client.api.inspect_container(container.id)
                state = inspected.get("State", {})
                name = inspected.get("Name", container.name).lstrip("/")
                asset_id = f"docker:{name}"
                previous_asset = asset_registry.get_asset(asset_id)
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
                    "asset_id": asset_id,
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
                pending_events.extend(self.transition_events_for(previous_asset, item))
                self.register_container_asset(item)
                items.append(item)
            items = sorted(items, key=lambda c: c["name"])
            self.publish(EventTypes.DOCKER_COLLECTED, "info", DOCKER_HOST_ASSET_ID, {"asset_id": DOCKER_HOST_ASSET_ID, "total": len(items), "docker_read_at": docker_read_at})
            for event_type, severity, payload in pending_events:
                self.publish(event_type, severity, payload["asset_id"], payload)
            return items, None
        except DockerException as exc:
            return [], str(exc)

    def collect(self) -> dict[str, Any]:
        containers, error = self.list_containers()
        return {"plugin": self.name, "error": error, "containers": containers}
