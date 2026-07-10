import tempfile
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.actions.engine import action_engine
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.main_auth import app


@contextmanager
def api_access_environment():
    previous_db = config.DB_PATH
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "api_access.db")
        init_db()
        initialize_auth_tables()
        action_engine.initialize()
        client = TestClient(app, follow_redirects=False)
        try:
            yield client
        finally:
            client.close()
            config.DB_PATH = previous_db


def credential():
    return "".join(["Technical", "Read", "Pass", "-42!"])


def login(client, role):
    username = f"technical-{role}"
    auth_service.create_user(username, f"Technical {role}", role, credential())
    response = client.post("/api/auth/login", json={"username": username, "password": credential()})
    assert response.status_code == 200, response.text


def test_anonymous_gets_only_redacted_health_and_mission_summaries():
    with api_access_environment() as client:
        actions = client.get("/api/actions")
        assert actions.status_code == 401
        assert actions.json() == {"detail": "Authentication required"}

        health = client.get("/api/health")
        assert health.status_code == 200
        assert set(health.json()) == {"status", "app", "version"}

        mission = client.get("/api/mission")
        assert mission.status_code == 200
        assert set(mission.json()) == {
            "status",
            "overall_status",
            "safe_mode",
            "docker",
            "active_incidents",
        }
        assert "containers" not in mission.json()
        assert "assets" not in mission.json()
        assert "events" not in mission.json()


def test_api_documentation_requires_owner():
    with api_access_environment() as client:
        for path in ["/openapi.json", "/docs", "/redoc"]:
            response = client.get(path)
            assert response.status_code == 401
            assert response.json() == {"detail": "Authentication required"}

    with api_access_environment() as client:
        login(client, "adult")
        assert client.get("/openapi.json").status_code == 403

    with api_access_environment() as client:
        login(client, "owner")
        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        assert schema.json()["info"]["title"] == config.APP_NAME
        assert client.get("/docs").status_code == 200


def test_non_owner_cannot_read_technical_apis():
    with api_access_environment() as client:
        login(client, "adult")
        response = client.get("/api/actions")
        assert response.status_code == 403
        assert response.json() == {"detail": "Owner role required"}
        assert "containers" not in client.get("/api/mission").json()
        assert "cpu_percent" not in client.get("/api/health").json()


def test_owner_can_read_technical_apis_and_full_health():
    with api_access_environment() as client:
        login(client, "owner")
        actions = client.get("/api/actions")
        assert actions.status_code == 200
        assert actions.json() == {"actions": []}

        health = client.get("/api/health")
        assert health.status_code == 200
        assert "cpu_percent" in health.json()
        assert "memory" in health.json()


def test_static_assets_are_revalidated_after_deploy():
    with api_access_environment() as client:
        response = client.get("/static/js/wall-safety.js")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache, must-revalidate"


def test():
    test_anonymous_gets_only_redacted_health_and_mission_summaries()
    test_api_documentation_requires_owner()
    test_non_owner_cannot_read_technical_apis()
    test_owner_can_read_technical_apis_and_full_health()
    test_static_assets_are_revalidated_after_deploy()
    print("API read access tests OK")


if __name__ == "__main__":
    test()
