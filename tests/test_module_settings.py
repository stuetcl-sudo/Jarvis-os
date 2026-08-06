import tempfile
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.family_view import render_family_page
from app.family_visibility import save_visibility_rules
from app.main_auth import app
from app.module_settings import MODULES, load_module_settings, save_module_settings


ROOT = Path(__file__).resolve().parents[1]


def password():
    return "".join(["Module", "Settings", "Pass", "-42!"])


@contextmanager
def module_environment():
    previous = config.DB_PATH
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "modules.db")
        init_db()
        initialize_auth_tables()
        try:
            yield
        finally:
            config.DB_PATH = previous


def authenticated_client(role):
    client = TestClient(app, follow_redirects=False)
    username = f"modules-{role}"
    auth_service.create_user(username, f"Modules {role}", role, password())
    assert client.post("/api/auth/login", json={"username": username, "password": password()}).status_code == 200
    profile = client.get("/api/auth/me")
    assert profile.status_code == 200
    return client, profile.json()["csrf_token"]


def test_all_modules_are_enabled_by_default():
    with module_environment():
        settings = load_module_settings(db_path=config.DB_PATH)
        assert tuple(settings) == MODULES
        assert all(settings.values())
        page = render_family_page({"role": "owner", "display_name": "Owner"})
        for selector in ('data-family-card="calendar"', 'data-family-card="tasks"', 'data-family-card="routine"', 'data-family-card="meal"', 'data-family-card="weather"', 'id="wallSafetyStrip"'):
            assert selector in page


def test_owner_can_read_and_update_module_settings():
    with module_environment():
        client, csrf = authenticated_client("owner")
        try:
            response = client.get("/api/admin/modules")
            assert response.status_code == 200 and all(response.json()["modules"].values())
            modules = {module: module not in {"tasks", "weather"} for module in MODULES}
            saved = client.post("/api/admin/modules", json={"modules": modules}, headers={"X-CSRF-Token": csrf})
            assert saved.status_code == 200
            assert saved.json()["modules"] == modules
            assert client.get("/api/admin/modules").json()["modules"] == modules
        finally:
            client.close()


def test_non_owner_cannot_read_or_update_module_settings():
    with module_environment():
        for role in ("adult", "child", "wall_display"):
            client, csrf = authenticated_client(role)
            try:
                assert client.get("/api/admin/modules").status_code == 403
                response = client.post(
                    "/api/admin/modules",
                    json={"modules": {module: False for module in MODULES}},
                    headers={"X-CSRF-Token": csrf},
                )
                assert response.status_code == 403
                assert all(load_module_settings(db_path=config.DB_PATH).values())
            finally:
                client.close()


def test_disabled_modules_are_omitted_from_family_page():
    with module_environment():
        save_module_settings({module: module in {"calendar", "weather"} for module in MODULES}, db_path=config.DB_PATH)
        page = render_family_page({"role": "owner", "display_name": "Owner"})
        assert 'data-family-modules="calendar,weather"' in page
        assert 'data-family-card="calendar"' in page
        assert 'data-family-card="weather"' in page
        for selector in ('data-family-card="tasks"', 'data-family-card="routine"', 'data-family-card="meal"', 'id="wallSafetyStrip"', 'id="routineEditor"'):
            assert selector not in page


def test_disabled_modules_have_frontend_fetch_guards():
    family = (ROOT / "app/static/js/family.js").read_text(encoding="utf-8")
    meals = (ROOT / "app/static/js/family-meals.js").read_text(encoding="utf-8")
    tasks = (ROOT / "app/static/js/family-tasks.js").read_text(encoding="utf-8")
    routines = (ROOT / "app/static/js/routines.js").read_text(encoding="utf-8")
    uv = (ROOT / "app/static/js/family-uv.js").read_text(encoding="utf-8")
    safety = (ROOT / "app/static/js/wall-safety.js").read_text(encoding="utf-8")
    assert 'familyModuleEnabled("weather")\n      ? refreshSource("/api/family/weather"' in family
    assert 'familyModuleEnabled("calendar")\n      ? refreshSource("/api/family/calendar"' in family
    assert 'if (!familyModuleEnabled("meal_plan")) return' in meals
    assert 'if (!familyModuleEnabled("tasks")) return' in tasks
    assert 'if (familyModuleEnabled("routines"))' in routines
    assert 'if (!familyModuleEnabled("weather")) return' in uv
    assert 'familyModuleEnabled("safety")' in safety


def test_existing_visibility_and_frontend_safety_are_preserved():
    with module_environment():
        save_visibility_rules({"child": {"calendar": False}}, db_path=config.DB_PATH)
        page = render_family_page({"role": "child", "display_name": "Child"})
        assert 'body[data-family-role="child"] [data-family-card="calendar"]{display:none!important}' in page
        assert 'data-family-card="calendar"' in page
    admin = (ROOT / "app/static/js/admin-modules.js").read_text(encoding="utf-8")
    assert 'getJson("/api/admin/modules"' in admin
    assert 'method: "POST"' in admin
    assert "innerHTML" not in admin
    assert "onclick=" not in admin
    assert "credentials" not in admin


def test():
    test_all_modules_are_enabled_by_default()
    test_owner_can_read_and_update_module_settings()
    test_non_owner_cannot_read_or_update_module_settings()
    test_disabled_modules_are_omitted_from_family_page()
    test_disabled_modules_have_frontend_fetch_guards()
    test_existing_visibility_and_frontend_safety_are_preserved()
    print("Module settings tests OK")


if __name__ == "__main__":
    test()
