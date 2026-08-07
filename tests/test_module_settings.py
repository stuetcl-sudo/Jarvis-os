import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import config
from app.calendar import calendar_window
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.family_view import render_family_page
from app.family_visibility import save_visibility_rules
from app.main_auth import app
from app.meal_plan import MealPlanService
from app.module_settings import DEFAULT_MODULE_CONFIG, MODULES, load_module_config, load_module_settings, save_module_config, save_module_settings


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
        assert load_module_config(db_path=config.DB_PATH) == DEFAULT_MODULE_CONFIG
        page = render_family_page({"role": "owner", "display_name": "Owner"})
        for selector in ('data-family-card="calendar"', 'data-family-card="tasks"', 'data-family-card="routine"', 'data-family-card="meal"', 'data-family-card="weather"', 'id="wallSafetyStrip"'):
            assert selector in page


def test_owner_can_read_and_update_module_settings():
    with module_environment():
        client, csrf = authenticated_client("owner")
        try:
            response = client.get("/api/admin/modules")
            assert response.status_code == 200 and all(response.json()["modules"].values())
            assert response.json()["config"] == DEFAULT_MODULE_CONFIG
            modules = {module: module not in {"tasks", "weather"} for module in MODULES}
            module_config = {"calendar_days": 5, "meal_plan_days": 4, "weather_uv_enabled": False}
            saved = client.post("/api/admin/modules", json={"modules": modules, "config": module_config}, headers={"X-CSRF-Token": csrf})
            assert saved.status_code == 200
            assert saved.json()["modules"] == modules
            assert saved.json()["config"] == module_config
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
                    json={"modules": {module: False for module in MODULES}, "config": {"calendar_days": 1}},
                    headers={"X-CSRF-Token": csrf},
                )
                assert response.status_code == 403
                assert all(load_module_settings(db_path=config.DB_PATH).values())
                assert load_module_config(db_path=config.DB_PATH) == DEFAULT_MODULE_CONFIG
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


def test_module_config_is_bounded_and_applied_to_family_page():
    with module_environment():
        assert save_module_config({"calendar_days": 99, "meal_plan_days": -2, "weather_uv_enabled": False}, db_path=config.DB_PATH) == {
            "calendar_days": 7, "meal_plan_days": 1, "weather_uv_enabled": False,
        }
        page = render_family_page({"role": "owner", "display_name": "Owner"})
        assert 'data-calendar-days="7"' in page
        assert 'data-meal-plan-days="1"' in page
        assert 'data-weather-uv-enabled="false"' in page


def test_calendar_days_control_the_requested_window():
    start, end, _, _ = calendar_window(5, datetime(2026, 8, 7, 12, tzinfo=timezone.utc))
    assert end - start == timedelta(days=5)
    calendar_frontend = (ROOT / "app/static/js/family-calendar.js").read_text(encoding="utf-8")
    assert "Number(document.body.dataset.calendarDays) || 3" in calendar_frontend
    assert "calendarRangeKeys(calendarVisibleDays, now)" in calendar_frontend


def test_meal_plan_days_limit_output():
    now = datetime(2026, 8, 7, 12, tzinfo=timezone.utc)
    events = []
    for offset in range(7):
        start = now.replace(hour=18) + timedelta(days=offset)
        events.append({"title": f"Ret {offset}", "start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(), "all_day": False})

    class CalendarStub:
        def get_calendar(self, _user):
            return {"status": "ok", "events": events, "stale": False}

    service = MealPlanService(
        calendar_service=CalendarStub(),
        settings_loader=lambda: SimpleNamespace(lookahead_days=7),
        now_provider=lambda: now,
    )
    result = service.get_meal_plan({"role": "owner"}, display_days=2)
    assert len(result["days"]) == 2
    assert result["today"] == ["Ret 0"]


def test_uv_can_be_disabled_before_frontend_fetching():
    uv = (ROOT / "app/static/js/family-uv.js").read_text(encoding="utf-8")
    toggle = uv.index('document.body.dataset.weatherUvEnabled === "false"')
    fetch = uv.index('fetch("/api/family/weather"')
    assert toggle < fetch
    assert "return;" in uv[toggle:fetch]


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
    test_module_config_is_bounded_and_applied_to_family_page()
    test_calendar_days_control_the_requested_window()
    test_meal_plan_days_limit_output()
    test_uv_can_be_disabled_before_frontend_fetching()
    test_disabled_modules_have_frontend_fetch_guards()
    test_existing_visibility_and_frontend_safety_are_preserved()
    print("Module settings tests OK")


if __name__ == "__main__":
    test()
