import tempfile
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.family_visibility import save_visibility_rules
from app.main_auth import app


@contextmanager
def api_visibility_environment():
    previous_db = config.DB_PATH
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "family_visibility_api.db")
        init_db()
        initialize_auth_tables()
        client = TestClient(app, follow_redirects=False)
        try:
            yield client
        finally:
            client.close()
            config.DB_PATH = previous_db


def credential():
    return "".join(["Family", "Visibility", "Pass", "-42!"])


def login(client, role):
    username = f"visibility-{role}"
    auth_service.create_user(username, f"Visibility {role}", role, credential())
    response = client.post("/api/auth/login", json={"username": username, "password": credential()})
    assert response.status_code == 200, response.text
    profile = client.get("/api/auth/me")
    assert profile.status_code == 200
    return profile.json()["csrf_token"]


def hide_all_child_family_features():
    save_visibility_rules(
        {
            "child": {
                "calendar": False,
                "weather": False,
                "meal": False,
                "tasks": False,
                "safety": False,
            }
        },
        db_path=config.DB_PATH,
    )


def test_anonymous_cannot_read_household_safety_status():
    with api_visibility_environment() as client:
        response = client.get("/api/family/safety-status")
        assert response.status_code == 401
        assert response.json() == {"detail": "Authentication required"}


def test_hidden_family_features_return_hidden_payloads_for_child():
    with api_visibility_environment() as client:
        hide_all_child_family_features()
        login(client, "child")

        calendar = client.get("/api/family/calendar")
        assert calendar.status_code == 200
        assert calendar.json()["status"] == "hidden"
        assert calendar.json()["events"] == []
        assert calendar.json()["calendars"] == []

        weather = client.get("/api/family/weather")
        assert weather.status_code == 200
        assert weather.json()["status"] == "hidden"
        assert weather.json()["forecast"] == []
        assert weather.json()["temperature"] is None

        meal = client.get("/api/family/meal-plan")
        assert meal.status_code == 200
        assert meal.json() == {"status": "hidden", "days": [], "today": [], "stale": False}

        tasks = client.get("/api/family/tasks")
        assert tasks.status_code == 200
        assert tasks.json()["status"] == "hidden"
        assert tasks.json()["lists"] == []
        assert tasks.json()["can_add"] is False
        assert tasks.json()["can_complete"] is False

        safety = client.get("/api/family/safety-status")
        assert safety.status_code == 200
        assert safety.json()["status"] == "hidden"
        assert safety.json()["doors"] == {"status": "unknown", "label": "Skjult"}


def test_hidden_tasks_cannot_be_changed_even_with_csrf():
    with api_visibility_environment() as client:
        hide_all_child_family_features()
        csrf = login(client, "child")
        response = client.post(
            "/api/family/tasks/indkob/items",
            headers={"X-CSRF-Token": csrf},
            json={"summary": "Kakao", "description": None},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Task access is hidden"


def test_owner_is_not_limited_by_family_visibility_rules():
    with api_visibility_environment() as client:
        hide_all_child_family_features()
        login(client, "owner")
        for endpoint in [
            "/api/family/calendar",
            "/api/family/weather",
            "/api/family/meal-plan",
            "/api/family/tasks",
            "/api/family/safety-status",
        ]:
            response = client.get(endpoint)
            assert response.status_code == 200
            assert response.json()["status"] != "hidden"


if __name__ == "__main__":
    test_anonymous_cannot_read_household_safety_status()
    test_hidden_family_features_return_hidden_payloads_for_child()
    test_hidden_tasks_cannot_be_changed_even_with_csrf()
    test_owner_is_not_limited_by_family_visibility_rules()
    print("Family API visibility tests OK")
