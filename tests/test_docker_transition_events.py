import tempfile
from pathlib import Path
from unittest.mock import patch

from app import config
from app.assets.registry import initialize_asset_tables
from app.assets.relationships import initialize_relationship_tables
from app.db import init_db
from app.events.types import EventTypes
from app.plugins.docker_plugin import DockerPlugin
from app.policies.rules import default_policies


class FakeContainer:
    def __init__(self, name, state):
        self.name = name
        self.id = f"{name}-id"
        self.short_id = name[:12]
        self.status = state
        self._state = state

    def reload(self):
        self.status = self._state


class FakeContainerCollection:
    def __init__(self, containers):
        self._containers = containers

    def list(self, all=True):
        return self._containers


class FakeAPI:
    def __init__(self, containers):
        self._containers = {container.id: container for container in containers}

    def inspect_container(self, container_id):
        container = self._containers[container_id]
        return {
            "Name": f"/{container.name}",
            "State": {"Status": container._state, "RestartCount": 0},
            "Config": {"Image": "example/image:latest"},
            "Created": "2026-01-01T00:00:00Z",
        }


class FakeDockerClient:
    def __init__(self, containers):
        self.containers = FakeContainerCollection(containers)
        self.api = FakeAPI(containers)


def reset_config():
    config.CRITICAL_SERVICES = set()
    config.OPTIONAL_SERVICES = set()
    config.IGNORED_SERVICES = set()
    config.PROTECTED_CONTAINERS = set()
    config.ALLOWED_AUTO_START_CONTAINERS = set()
    config.ASSET_DEPENDENCIES = []


def reset_db():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    config.DB_PATH = tmp.name
    reset_config()
    init_db()
    initialize_asset_tables()
    initialize_relationship_tables()
    return Path(tmp.name)


def set_classifications(classifications=None):
    reset_config()
    classifications = classifications or {}
    for name, classification in classifications.items():
        if classification == "critical":
            config.CRITICAL_SERVICES.add(name)
        elif classification == "optional":
            config.OPTIONAL_SERVICES.add(name)
        elif classification == "stopped_by_design":
            config.IGNORED_SERVICES.add(name)


def collect_for(container, classifications=None):
    set_classifications(classifications)
    plugin = DockerPlugin()
    events = []
    plugin.publish = lambda event_type, severity="info", service=None, payload=None, asset_id=None: events.append(event_type)
    with patch.object(plugin, "client", return_value=FakeDockerClient([container])):
        plugin.list_containers()
    return events


def count(events, event_type):
    return len([event for event in events if event == event_type])


def test_first_running_observation_does_not_publish_started_repeatedly():
    path = reset_db()
    try:
        first = collect_for(FakeContainer("example-app", "running"), {"example-app": "optional"})
        second = collect_for(FakeContainer("example-app", "running"), {"example-app": "optional"})
        assert count(first, EventTypes.DOCKER_COLLECTED) == 1
        assert count(first, EventTypes.CONTAINER_DISCOVERED) == 1
        assert count(first, EventTypes.CONTAINER_STARTED) == 0
        assert count(second, EventTypes.DOCKER_COLLECTED) == 1
        assert count(second, EventTypes.CONTAINER_STARTED) == 0
        assert count(second, EventTypes.CONTAINER_STOPPED) == 0
    finally:
        path.unlink(missing_ok=True)


def test_running_to_running_publishes_no_transition():
    path = reset_db()
    try:
        collect_for(FakeContainer("example-app", "running"), {"example-app": "optional"})
        events = collect_for(FakeContainer("example-app", "running"), {"example-app": "optional"})
        assert count(events, EventTypes.CONTAINER_STARTED) == 0
        assert count(events, EventTypes.CONTAINER_STOPPED) == 0
    finally:
        path.unlink(missing_ok=True)


def test_running_to_exited_publishes_one_stopped():
    path = reset_db()
    try:
        collect_for(FakeContainer("example-app", "running"), {"example-app": "optional"})
        events = collect_for(FakeContainer("example-app", "exited"), {"example-app": "optional"})
        assert count(events, EventTypes.CONTAINER_STOPPED) == 1
        assert count(events, EventTypes.CONTAINER_STARTED) == 0
    finally:
        path.unlink(missing_ok=True)


def test_exited_to_exited_publishes_no_transition():
    path = reset_db()
    try:
        collect_for(FakeContainer("example-app", "exited"), {"example-app": "optional"})
        events = collect_for(FakeContainer("example-app", "exited"), {"example-app": "optional"})
        assert count(events, EventTypes.CONTAINER_STOPPED) == 0
        assert count(events, EventTypes.CONTAINER_STARTED) == 0
    finally:
        path.unlink(missing_ok=True)


def test_exited_to_running_publishes_one_started():
    path = reset_db()
    try:
        collect_for(FakeContainer("example-app", "exited"), {"example-app": "optional"})
        events = collect_for(FakeContainer("example-app", "running"), {"example-app": "optional"})
        assert count(events, EventTypes.CONTAINER_STARTED) == 1
        assert count(events, EventTypes.CONTAINER_STOPPED) == 0
    finally:
        path.unlink(missing_ok=True)


def test_new_unknown_asset_publishes_unknown_once():
    path = reset_db()
    try:
        first = collect_for(FakeContainer("example-app", "running"))
        second = collect_for(FakeContainer("example-app", "running"))
        assert count(first, EventTypes.CONTAINER_UNKNOWN) == 1
        assert count(second, EventTypes.CONTAINER_UNKNOWN) == 0
    finally:
        path.unlink(missing_ok=True)


def test_classified_to_unknown_publishes_unknown_once():
    path = reset_db()
    try:
        collect_for(FakeContainer("example-app", "running"), {"example-app": "optional"})
        first_unknown = collect_for(FakeContainer("example-app", "running"))
        repeated_unknown = collect_for(FakeContainer("example-app", "running"))
        assert count(first_unknown, EventTypes.CONTAINER_UNKNOWN) == 1
        assert count(repeated_unknown, EventTypes.CONTAINER_UNKNOWN) == 0
    finally:
        path.unlink(missing_ok=True)


def test_stopped_discovery_policy_behavior_remains_available():
    policies = default_policies()
    discovered_stopped = [p for p in policies if p["trigger_event_type"] == EventTypes.CONTAINER_DISCOVERED and p["conditions"].get("state") == "exited"]
    classifications = {p["conditions"].get("classification") for p in discovered_stopped}
    assert "critical" in classifications
    assert "optional" in classifications


def test_docker_collected_is_published_each_scan():
    path = reset_db()
    try:
        first = collect_for(FakeContainer("example-app", "running"), {"example-app": "optional"})
        second = collect_for(FakeContainer("example-app", "running"), {"example-app": "optional"})
        assert count(first, EventTypes.DOCKER_COLLECTED) == 1
        assert count(second, EventTypes.DOCKER_COLLECTED) == 1
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    for test in [
        test_first_running_observation_does_not_publish_started_repeatedly,
        test_running_to_running_publishes_no_transition,
        test_running_to_exited_publishes_one_stopped,
        test_exited_to_exited_publishes_no_transition,
        test_exited_to_running_publishes_one_started,
        test_new_unknown_asset_publishes_unknown_once,
        test_classified_to_unknown_publishes_unknown_once,
        test_stopped_discovery_policy_behavior_remains_available,
        test_docker_collected_is_published_each_scan,
    ]:
        test()
    print("Docker transition event tests OK")
