import tempfile
from pathlib import Path
from unittest.mock import patch

from app import config
from app.actions.engine import action_engine
from app.actions.history import initialize_action_tables, list_actions
from app.assets.registry import asset_registry, initialize_asset_tables
from app.db import init_db
from app.safety import can_auto_start
from app.worker import auto_heal


def reset_db():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    config.DB_PATH = tmp.name
    config.SAFE_MODE = True
    config.ALLOW_RESTART_STOPPED = True
    config.AUTO_START_FAILURE_LIMIT = 3
    config.AUTO_START_FAILURE_WINDOW_MINUTES = 30
    config.PROTECTED_CONTAINERS = set()
    config.ASSET_DEPENDENCIES = []
    init_db()
    initialize_asset_tables()
    initialize_action_tables()
    return Path(tmp.name)


def register_asset(asset_id, state, classification="optional", auto_actions_allowed=True):
    name = asset_id.split(":", 1)[-1]
    return asset_registry.register_asset(
        {
            "asset_id": asset_id,
            "asset_type": "docker_container",
            "plugin": "docker",
            "name": name,
            "display_name": name,
            "state": state,
            "health": None,
            "classification": classification,
            "protected": False,
            "auto_actions_allowed": auto_actions_allowed,
            "metadata": {},
        }
    )


def stopped_container(asset_id="docker:example-app"):
    return {
        "id": "example-id",
        "name": asset_id.split(":", 1)[-1],
        "asset_id": asset_id,
        "status": "exited",
        "docker_state": "exited",
        "protected": False,
        "classification": "optional",
        "auto_start_allowed": True,
    }


def configure_dependency(dependency_state):
    source_id = "docker:example-app"
    dependency_id = "docker:example-network"
    register_asset(source_id, "exited")
    register_asset(dependency_id, dependency_state, classification="critical", auto_actions_allowed=False)
    config.ASSET_DEPENDENCIES = [(source_id, dependency_id)]
    return source_id, dependency_id


def test_generic_dependency_defaults_to_running_without_service_names():
    path = reset_db()
    try:
        source_id, dependency_id = configure_dependency("running")
        assert config.ASSET_DEPENDENCIES == [(source_id, dependency_id)]
        allowed, _ = can_auto_start(stopped_container(source_id), [], 0)
        assert allowed is True
    finally:
        path.unlink(missing_ok=True)


def test_unavailable_dependency_prevents_worker_queue_and_action_run():
    path = reset_db()
    try:
        source_id, _ = configure_dependency("exited")
        item = stopped_container(source_id)
        allowed, _ = can_auto_start(item, [], 0)
        assert allowed is False

        auto_heal([item])
        assert list_actions(10) == []

        queued = action_engine.queue_action(
            asset_id=source_id,
            action_type="docker.start_container",
            requested_by="worker",
            source="worker",
            reason="generic dependency safety test",
            requires_approval=True,
        )
        action_engine.approve_action(queued["action_id"], "test")
        with patch("app.actions.engine.execute_action") as execute_mock:
            result = action_engine.run_action(queued["action_id"])
        assert result["status"] == "denied"
        assert result["safety_status"] == "denied"
        execute_mock.assert_not_called()
    finally:
        path.unlink(missing_ok=True)


def test_available_dependency_permits_normal_approved_path():
    path = reset_db()
    try:
        source_id, _ = configure_dependency("running")
        auto_heal([stopped_container(source_id)])
        actions = list_actions(10)
        assert len(actions) == 1
        assert actions[0]["status"] == "waiting_approval"

        action_engine.approve_action(actions[0]["action_id"], "test")
        with patch("app.actions.engine.execute_action", return_value=(True, {"status": "simulated"}, "simulated executor")) as execute_mock:
            result = action_engine.run_action(actions[0]["action_id"])
        assert result["status"] == "completed"
        assert result["safety_status"] == "passed"
        execute_mock.assert_called_once()
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    for test in [
        test_generic_dependency_defaults_to_running_without_service_names,
        test_unavailable_dependency_prevents_worker_queue_and_action_run,
        test_available_dependency_permits_normal_approved_path,
    ]:
        test()
    print("Generic dependency safety tests OK")
