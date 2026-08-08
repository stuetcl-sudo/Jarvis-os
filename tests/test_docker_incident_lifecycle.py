import tempfile
from pathlib import Path
from unittest.mock import patch

from app import config
from app.db import init_db, list_incidents
from app.main import incidents
from app.worker import run_check_once


DOCKER_INCIDENT_TITLE = "Docker kan ikke læses"


def healthy_containers():
    return [
        {
            "name": f"service-{index}",
            "status": "running",
            "docker_state": "running",
            "classification": "unknown",
        }
        for index in range(10)
    ]


def healthy_system():
    return {
        "cpu_percent": 10.0,
        "memory": {"percent": 20.0},
        "swap": {"percent": 0.0},
        "disk_root": {"percent": 30.0},
        "warnings": [],
    }


def test_docker_read_incident_is_resolved_after_successful_inventory():
    previous_db_path = config.DB_PATH
    database = tempfile.NamedTemporaryFile(delete=False)
    database.close()
    config.DB_PATH = database.name
    init_db()
    try:
        reads = [
            ([], "502 Server Error: Docker Engine is unavailable"),
            (healthy_containers(), None),
            (healthy_containers(), None),
        ]
        with (
            patch("app.worker.list_containers", side_effect=reads),
            patch("app.worker.get_health", return_value=healthy_system()),
            patch("app.worker.register_system_health_assets"),
            patch("app.worker.publish"),
            patch("app.worker.evaluate_incidents"),
            patch("app.worker.learn_from_check"),
            patch("app.worker.auto_heal"),
            patch("app.worker.safe_cleanup_old_rows", return_value={}),
        ):
            try:
                run_check_once()
            except RuntimeError as exc:
                assert "Docker Engine is unavailable" in str(exc)
            else:
                raise AssertionError("A failed Docker read must fail the worker check")

            active = list_incidents(active_only=True)
            assert len(active) == 1
            assert active[0]["service"] == "docker"
            assert active[0]["title"] == DOCKER_INCIDENT_TITLE
            assert active[0]["status"] == "active"

            run_check_once()

            assert incidents(active_only=True)["incidents"] == []
            history = list_incidents(active_only=False)
            assert len(history) == 1
            assert history[0]["status"] == "resolved"
            assert history[0]["resolved_at"] is not None

            run_check_once()

            assert incidents(active_only=True)["incidents"] == []
            assert len(list_incidents(active_only=False)) == 1
    finally:
        config.DB_PATH = previous_db_path
        Path(database.name).unlink(missing_ok=True)


if __name__ == "__main__":
    test_docker_read_incident_is_resolved_after_successful_inventory()
    print("Docker incident lifecycle tests OK")
