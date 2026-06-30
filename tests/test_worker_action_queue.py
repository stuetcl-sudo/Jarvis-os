import tempfile
from pathlib import Path
from unittest.mock import patch

from app import config
from app.actions.engine import action_engine
from app.actions.history import initialize_action_tables, list_actions
from app.assets.registry import initialize_asset_tables
from app.assets.relationships import initialize_relationship_tables
from app.db import init_db
from app.events.types import EventTypes
from app.plugins.docker_plugin import DockerPlugin
from app.worker import auto_heal


class FakeContainer:
    def __init__(self, name, state):
        self.name = name
        self.id = f"{name}-id"
        self.short_id = name[:12]
        self.status = state
        self._state = state
        self.started = False

    def reload(self):
        self.status = self._state

    def start(self):
        self.started = True
        raise AssertionError("Worker must not call Docker container.start() directly")


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


def reset_db():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    config.DB_PATH = tmp.name
    config.SAFE_MODE = True
    config.ALLOW_RESTART_STOPPED = True
    config.AUTO_START_FAILURE_LIMIT = 3
    config.AUTO_START_FAILURE_WINDOW_MINUTES = 30
    config.CRITICAL_SERVICES = set()
    config.OPTIONAL_SERVICES = set()
    config.IGNORED_SERVICES = set()
    config.PROTECTED_CONTAINERS = set()
    config.ALLOWED_AUTO_START_CONTAINERS = set()
    config.ASSET_DEPENDENCIES = []
    init_db()
    initialize_asset_tables()
    initialize_relationship_tables()
    initialize_action_tables()
    return Path(tmp.name)


def eligible_container():
    return {
        "id": "example-id",
        "name": "example-app",
        "asset_id": "docker:example-app",
        "image": "example/image:latest",
        "status": "exited",
        "docker_state": "exited",
        "docker_status": "exited",
        "health_status": None,
        "read_at": "2026-01-01T00:00:00+00:00",
        "created": "2026-01-01T00:00:00Z",
        "restart_count": 0,
        "protected": False,
        "classification": "optional",
        "auto_start_allowed": True,
    }


def test_worker_queues_waiting_approval_action_instead_of_direct_start():
    path = reset_db()
    try:
        container = FakeContainer("example-app", "exited")
        with patch("docker.from_env", return_value=FakeDockerClient([container])):
            with patch("app.actions.engine.publish") as publish_mock:
                auto_heal([eligible_container()])
        actions = list_actions(10)
        assert len(actions) == 1
        assert actions[0]["action_type"] == "docker.start_container"
        assert actions[0]["source"] == "worker"
        assert actions[0]["requested_by"] == "worker"
        assert actions[0]["requires_approval"] is True
        assert actions[0]["approved"] is False
        assert actions[0]["status"] == "waiting_approval"
        assert container.started is False
        assert all(call.args[1] != EventTypes.CONTAINER_STARTED for call in publish_mock.call_args_list)
    finally:
        path.unlink(missing_ok=True)


def test_repeated_worker_checks_do_not_create_duplicate_actions():
    path = reset_db()
    try:
        auto_heal([eligible_container()])
        auto_heal([eligible_container()])
        actions = list_actions(10)
        assert len(actions) == 1
        assert actions[0]["status"] == "waiting_approval"
    finally:
        path.unlink(missing_ok=True)


def test_live_exited_to_running_scan_emits_one_container_started():
    path = reset_db()
    try:
        config.OPTIONAL_SERVICES.add("example-app")
        plugin = DockerPlugin()
        events = []
        plugin.publish = lambda event_type, severity="info", service=None, payload=None, asset_id=None: events.append(event_type)
        with patch.object(plugin, "client", return_value=FakeDockerClient([FakeContainer("example-app", "exited")])):
            plugin.list_containers()
        with patch.object(plugin, "client", return_value=FakeDockerClient([FakeContainer("example-app", "running")])):
            plugin.list_containers()
        assert events.count(EventTypes.CONTAINER_STARTED) == 1
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    for test in [
        test_worker_queues_waiting_approval_action_instead_of_direct_start,
        test_repeated_worker_checks_do_not_create_duplicate_actions,
        test_live_exited_to_running_scan_emits_one_container_started,
    ]:
        test()
    print("Worker Action Engine queue tests OK")
