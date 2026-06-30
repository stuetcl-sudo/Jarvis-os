import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

try:
    import docker  # noqa: F401
except ModuleNotFoundError:
    docker_module = ModuleType("docker")
    docker_errors = ModuleType("docker.errors")

    class DockerException(Exception):
        pass

    class NotFound(DockerException):
        pass

    docker_module.from_env = Mock()
    docker_module.errors = docker_errors
    docker_errors.DockerException = DockerException
    docker_errors.NotFound = NotFound
    sys.modules["docker"] = docker_module
    sys.modules["docker.errors"] = docker_errors

from app import config
from app.actions.action import Action
from app.actions.engine import action_engine
from app.actions.executors import execute_docker_start
from app.actions.history import initialize_action_tables, insert_action
from app.actions.verification import _env_bounded_float, verify_docker_state


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def running_container(name="example-app"):
    return {"name": name, "docker_state": "running", "status": "Up"}


def exited_container(name="example-app"):
    return {"name": name, "docker_state": "exited", "status": "Exited"}


def docker_client(before_state="exited"):
    container = Mock()
    container.id = "container-id"
    client = Mock()
    client.containers.get.return_value = container
    client.api.inspect_container.return_value = {"State": {"Status": before_state}}
    return client, container


def reset_db():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    config.DB_PATH = tmp.name
    initialize_action_tables()
    return Path(tmp.name)


def make_approved_action():
    return insert_action(
        Action(
            requested_by="test",
            source="test",
            asset_id="docker:example-app",
            action_type="docker.start_container",
            reason="test action",
            requires_approval=True,
            status="approved",
            approved=True,
            approved_by="test",
            approved_at="2026-01-01T00:00:00+00:00",
        )
    )


def test_already_running_succeeds_immediately():
    with patch("app.actions.verification.list_containers", return_value=([running_container()], None)) as read_state:
        with patch("app.actions.verification.time.monotonic", return_value=10.0):
            with patch("app.actions.verification.time.sleep") as sleep:
                ok, reason, result = verify_docker_state("docker:example-app", "running")
    assert ok is True
    assert reason == "Verified docker:example-app is running."
    assert result["observed_state"] == "running"
    assert read_state.call_count == 1
    sleep.assert_not_called()


def test_exited_then_running_succeeds_after_polling():
    clock = FakeClock()
    states = [([exited_container()], None), ([running_container()], None)]
    with patch("app.actions.verification.DOCKER_VERIFY_TIMEOUT_SECONDS", 5.0):
        with patch("app.actions.verification.DOCKER_VERIFY_INTERVAL_SECONDS", 1.0):
            with patch("app.actions.verification.list_containers", side_effect=states) as read_state:
                with patch("app.actions.verification.time.monotonic", side_effect=clock.monotonic):
                    with patch("app.actions.verification.time.sleep", side_effect=clock.sleep):
                        ok, _, result = verify_docker_state("docker:example-app", "running")
    assert ok is True
    assert result["observed_state"] == "running"
    assert read_state.call_count == 2
    assert clock.sleeps == [1.0]


def test_container_start_is_called_exactly_once():
    clock = FakeClock()
    client, container = docker_client()
    states = [([exited_container()], None), ([running_container()], None)]
    action = {"action_id": "action-id", "asset_id": "docker:example-app", "action_type": "docker.start_container"}
    with patch("app.actions.verification.DOCKER_VERIFY_TIMEOUT_SECONDS", 5.0):
        with patch("app.actions.verification.DOCKER_VERIFY_INTERVAL_SECONDS", 1.0):
            with patch("app.actions.executors.docker.from_env", return_value=client):
                with patch("app.actions.executors.publish"):
                    with patch("app.actions.verification.list_containers", side_effect=states):
                        with patch("app.actions.verification.time.monotonic", side_effect=clock.monotonic):
                            with patch("app.actions.verification.time.sleep", side_effect=clock.sleep):
                                ok, result, _ = execute_docker_start(action)
    assert ok is True
    assert result["verified"] is True
    container.start.assert_called_once_with()


def test_timeout_returns_failure_with_final_observed_state():
    clock = FakeClock()
    with patch("app.actions.verification.DOCKER_VERIFY_TIMEOUT_SECONDS", 2.5):
        with patch("app.actions.verification.DOCKER_VERIFY_INTERVAL_SECONDS", 1.0):
            with patch("app.actions.verification.list_containers", return_value=([exited_container()], None)) as read_state:
                with patch("app.actions.verification.time.monotonic", side_effect=clock.monotonic):
                    with patch("app.actions.verification.time.sleep", side_effect=clock.sleep):
                        ok, reason, result = verify_docker_state("docker:example-app", "running")
    assert ok is False
    assert "is exited, expected running" in reason
    assert result["observed_state"] == "exited"
    assert read_state.call_count == 4
    assert clock.sleeps == [1.0, 1.0, 0.5]


def test_repeated_transient_read_errors_can_recover():
    clock = FakeClock()
    states = [([], "temporary-1"), ([], "temporary-2"), ([running_container()], None)]
    with patch("app.actions.verification.DOCKER_VERIFY_TIMEOUT_SECONDS", 5.0):
        with patch("app.actions.verification.DOCKER_VERIFY_INTERVAL_SECONDS", 1.0):
            with patch("app.actions.verification.list_containers", side_effect=states):
                with patch("app.actions.verification.time.monotonic", side_effect=clock.monotonic):
                    with patch("app.actions.verification.time.sleep", side_effect=clock.sleep):
                        ok, _, result = verify_docker_state("docker:example-app", "running")
    assert ok is True
    assert result["observed_state"] == "running"
    assert "verification_error" not in result
    assert clock.sleeps == [1.0, 1.0]


def test_persistent_read_errors_return_failure_with_final_error():
    clock = FakeClock()
    calls = {"count": 0}

    def failed_read():
        calls["count"] += 1
        return [], f"read-error-{calls['count']}"

    with patch("app.actions.verification.DOCKER_VERIFY_TIMEOUT_SECONDS", 2.0):
        with patch("app.actions.verification.DOCKER_VERIFY_INTERVAL_SECONDS", 1.0):
            with patch("app.actions.verification.list_containers", side_effect=failed_read):
                with patch("app.actions.verification.time.monotonic", side_effect=clock.monotonic):
                    with patch("app.actions.verification.time.sleep", side_effect=clock.sleep):
                        ok, reason, result = verify_docker_state("docker:example-app", "running")
    assert ok is False
    assert "read-error-3" in reason
    assert result["verification_error"] == "read-error-3"
    assert result["observed_state"] is None


def test_missing_container_can_appear_during_polling():
    clock = FakeClock()
    states = [([], None), ([running_container()], None)]
    with patch("app.actions.verification.DOCKER_VERIFY_TIMEOUT_SECONDS", 5.0):
        with patch("app.actions.verification.DOCKER_VERIFY_INTERVAL_SECONDS", 1.0):
            with patch("app.actions.verification.list_containers", side_effect=states):
                with patch("app.actions.verification.time.monotonic", side_effect=clock.monotonic):
                    with patch("app.actions.verification.time.sleep", side_effect=clock.sleep):
                        ok, _, result = verify_docker_state("docker:example-app", "running")
    assert ok is True
    assert result["observed_state"] == "running"
    assert clock.sleeps == [1.0]


def test_polling_uses_configured_timeout_and_interval():
    clock = FakeClock()
    with patch("app.actions.verification.DOCKER_VERIFY_TIMEOUT_SECONDS", 2.5):
        with patch("app.actions.verification.DOCKER_VERIFY_INTERVAL_SECONDS", 0.75):
            with patch("app.actions.verification.list_containers", return_value=([], None)) as read_state:
                with patch("app.actions.verification.time.monotonic", side_effect=clock.monotonic):
                    with patch("app.actions.verification.time.sleep", side_effect=clock.sleep):
                        ok, _, _ = verify_docker_state("docker:example-app", "running")
    assert ok is False
    assert read_state.call_count == 5
    assert clock.sleeps == [0.75, 0.75, 0.75, 0.25]
    assert clock.now == 2.5


def test_configuration_environment_overrides_are_positive_and_bounded():
    with patch.dict(os.environ, {"TEST_VERIFY_VALUE": "2.5"}):
        assert _env_bounded_float("TEST_VERIFY_VALUE", 1.0, 0.1, 10.0) == 2.5
    for value in ("0", "0.01", "-1", "10.1", "invalid"):
        with patch.dict(os.environ, {"TEST_VERIFY_VALUE": value}):
            assert _env_bounded_float("TEST_VERIFY_VALUE", 1.0, 0.1, 10.0) == 1.0


def test_action_engine_marks_failed_verification_as_failed():
    path = reset_db()
    clock = FakeClock()
    client, container = docker_client()
    try:
        action = make_approved_action()
        with patch("app.actions.verification.DOCKER_VERIFY_TIMEOUT_SECONDS", 1.0):
            with patch("app.actions.verification.DOCKER_VERIFY_INTERVAL_SECONDS", 1.0):
                with patch("app.actions.engine.check_action_safety", return_value=(True, "passed", "test safety passed")):
                    with patch("app.actions.engine.publish"), patch("app.actions.executors.publish"):
                        with patch("app.actions.executors.docker.from_env", return_value=client):
                            with patch("app.actions.verification.list_containers", return_value=([exited_container()], None)):
                                with patch("app.actions.verification.time.monotonic", side_effect=clock.monotonic):
                                    with patch("app.actions.verification.time.sleep", side_effect=clock.sleep):
                                        result = action_engine.run_action(action["action_id"])
        assert result["status"] == "failed"
        assert result["result"]["verified"] is False
        assert result["result"]["after"]["observed_state"] == "exited"
        container.start.assert_called_once_with()
    finally:
        path.unlink(missing_ok=True)


def test_action_engine_marks_successful_verification_as_completed():
    path = reset_db()
    client, container = docker_client()
    try:
        action = make_approved_action()
        with patch("app.actions.engine.check_action_safety", return_value=(True, "passed", "test safety passed")):
            with patch("app.actions.engine.publish"), patch("app.actions.executors.publish"):
                with patch("app.actions.executors.docker.from_env", return_value=client):
                    with patch("app.actions.verification.list_containers", return_value=([running_container()], None)):
                        result = action_engine.run_action(action["action_id"])
        assert result["status"] == "completed"
        assert result["result"]["verified"] is True
        assert result["result"]["after"]["observed_state"] == "running"
        container.start.assert_called_once_with()
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    for test in [
        test_already_running_succeeds_immediately,
        test_exited_then_running_succeeds_after_polling,
        test_container_start_is_called_exactly_once,
        test_timeout_returns_failure_with_final_observed_state,
        test_repeated_transient_read_errors_can_recover,
        test_persistent_read_errors_return_failure_with_final_error,
        test_missing_container_can_appear_during_polling,
        test_polling_uses_configured_timeout_and_interval,
        test_configuration_environment_overrides_are_positive_and_bounded,
        test_action_engine_marks_failed_verification_as_failed,
        test_action_engine_marks_successful_verification_as_completed,
    ]:
        test()
    print("Action verification tests OK")
