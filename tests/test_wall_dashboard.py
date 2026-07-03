import math
import tempfile
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.main_auth import app
from app.screen_registry import list_screens, upsert_screen
from app.wall_view import WALL_ROLES, render_wall_page
from app.weather import PUBLIC_FIELDS, _safe_uv_index, normalize_weather

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def wall_environment():
    previous = config.DB_PATH
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "wall.db")
        init_db()
        initialize_auth_tables()
        client = TestClient(app, follow_redirects=False)
        try:
            yield client
        finally:
            client.close()
            config.DB_PATH = previous


def credential():
    return "".join(["Wall", "Display", "Pass", "-42!"])


def login(client, role, display_name=None):
    username = f"wall-{role}"
    auth_service.create_user(username, display_name or f"Wall {role}", role, credential())
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": credential()},
    )
    assert response.status_code == 200, response.text
    profile = client.get("/api/auth/me")
    assert profile.status_code == 200, profile.text
    return profile.json().get("csrf_token") or profile.json().get("csrf_value")


def weather_payload():
    return {
        "state": "sunny",
        "attributes": {"temperature": 20, "temperature_unit": "°C"},
    }


def forecast_payload():
    return {"weather.example": {"forecast": []}}


def test_wall_route_roles_and_admin_policy():
    with wall_environment() as client:
        anonymous = client.get("/wall?role=owner")
        assert anonymous.status_code == 303
        assert anonymous.headers["location"] == "/login?next=/wall"

    for role in sorted(WALL_ROLES):
        with wall_environment() as client:
            login(client, role)
            wall = client.get("/wall?role=owner")
            assert wall.status_code == 200
            assert 'data-wall-dashboard="true"' in wall.text
            admin = client.get("/admin")
            assert admin.status_code == (200 if role == "owner" else 403)


def test_wall_reuses_family_dashboard_as_shared_display():
    for role in sorted(WALL_ROLES):
        with wall_environment() as client:
            login(client, role, "Private display name")
            page = client.get("/wall").text
            assert '<title>Jarvis – Vægskærm</title>' in page
            assert 'data-family-role="wall_display"' in page
            assert 'data-family-view="shared-display"' in page
            assert 'data-family-kiosk="true"' in page
            assert 'data-family-display-name=""' in page
            assert 'data-wall-screen-slug="wall"' in page
            assert 'data-wall-screen-name="Vægskærm"' in page
            assert "Private display name" not in page
            assert 'id="calendarRangeControls"' in page
            assert 'id="calendarEvents"' in page
            assert 'id="weatherData"' in page
            assert 'data-family-card="routine"' in page
            assert 'data-family-card="meal"' in page
            assert 'data-family-card="tasks"' in page
            assert '/static/js/family.js' in page
            assert '/static/js/family-calendar.js' in page
            assert '/static/js/routines.js' in page
            assert '/static/js/wall-mode.js' in page
            assert '/static/css/wall-mode.css' in page
            assert '/static/css/wall-profiles.css' in page
            assert '/static/js/wall.js' not in page
            assert 'class="wall-shell"' not in page
            assert "WALL_DISPLAY_ACTIONS" not in page
            assert ('href="/admin">Administration</a>' in page) is (role == "owner")


def test_named_wall_screens_are_stored_and_rendered():
    with wall_environment() as client:
        csrf = login(client, "owner")
        response = client.post(
            "/api/admin/screens",
            headers={"X-CSRF-Token": csrf},
            json={
                "name": "Wall Stuen",
                "slug": "wall-stuen",
                "screen_type": "wall-tablet",
                "modules": ["routine", "calendar", "weather"],
                "is_active": True,
            },
        )
        assert response.status_code == 200, response.text
        created = response.json()["screen"]
        assert created["url"] == "/wall/wall-stuen"
        assert created["modules"] == ["routine", "calendar", "weather"]

        listing = client.get("/api/admin/screens")
        assert listing.status_code == 200
        assert any(item["slug"] == "wall" for item in listing.json()["screens"])
        assert any(item["slug"] == "wall-stuen" for item in listing.json()["screens"])

        page = client.get("/wall/wall-stuen")
        assert page.status_code == 200
        assert '<title>Jarvis – Wall Stuen</title>' in page.text
        assert 'data-wall-screen-slug="wall-stuen"' in page.text
        assert 'data-wall-screen-name="Wall Stuen"' in page.text
        assert 'data-wall-preferred-profile="wall-tablet"' in page.text
        assert '[data-family-card="meal"]{display:none!important}' in page.text
        assert '[data-family-card="tasks"]{display:none!important}' in page.text


def test_named_wall_screen_access_policy_and_missing_screen():
    with wall_environment() as client:
        anonymous = client.get("/wall/stuen")
        assert anonymous.status_code == 303
        assert anonymous.headers["location"] == "/login?next=/wall/stuen"

    with wall_environment() as client:
        login(client, "adult")
        assert client.get("/wall/unknown").status_code == 404

    with wall_environment() as client:
        login(client, "adult")
        assert client.get("/api/admin/screens").status_code == 403


def test_wall_shared_display_hides_owner_technical_details():
    with wall_environment() as client:
        login(client, "owner")
        page = client.get("/wall").text
        for marker in [
            "Sikker tilstand",
            "Docker-systemer online",
            "Aktive hændelser",
            'data-family-section="technical-status"',
            'data-family-section="technical-system"',
            "<dt>CPU</dt>",
        ]:
            assert marker not in page


def test_wall_family_assets_are_available():
    with wall_environment() as client:
        login(client, "wall_display")
        for asset, marker in [
            ("/static/js/family.js", "renderCalendar"),
            ("/static/js/family-calendar.js", "calendarDayChoices"),
            ("/static/js/routines.js", "routineEndpoints"),
            ("/static/js/wall-mode.js", "requestFullscreen"),
            ("/static/css/family.css", ".family-shell"),
            ("/static/css/calendar-range.css", ".calendar-range-controls"),
            ("/static/css/wall-mode.css", 'body[data-wall-dashboard="true"]'),
            ("/static/css/wall-profiles.css", 'data-wall-screen-profile="tablet"'),
            ("/static/pictograms/routines.svg", 'symbol id="complete"'),
        ]:
            response = client.get(asset)
            assert response.status_code == 200, asset
            assert marker in response.text


def test_wall_mode_frontend_is_read_only_and_role_safe():
    javascript = (ROOT / "app/static/js/wall-mode.js").read_text(encoding="utf-8")
    view = (ROOT / "app/wall_view.py").read_text(encoding="utf-8")
    combined = javascript + view
    for forbidden in [
        "fetch(",
        "localStorage",
        "sessionStorage",
        "Authorization",
        "eval(",
        "innerHTML",
        "URLSearchParams",
    ]:
        assert forbidden not in combined
    assert "requestFullscreen" in javascript
    assert "fullscreenchange" in javascript
    assert 'role == "owner"' in view
    assert 'shared_display = {"role": "wall_display", "display_name": ""}' in view


def test_uv_backend_validation_and_categories_remain_strict():
    valid_values = [(0, 0), ("0", 0), (2, 2), ("5.5", 5.5), (11, 11)]
    for supplied, expected in valid_values:
        assert _safe_uv_index(supplied) == expected
        normalized = normalize_weather(
            weather_payload(),
            forecast_payload(),
            "weather.example",
            {"entity_id": "sensor.openuv_current_uv_index", "state": supplied},
        )
        assert normalized["uv_index"] == expected
        assert set(normalized) == PUBLIC_FIELDS

    for invalid in [None, "", True, False, "invalid", -1, float("nan"), float("inf")]:
        assert _safe_uv_index(invalid) is None
    assert math.isfinite(float(_safe_uv_index("7")))


def test_wall_defaults_to_three_calendar_days_and_remains_responsive():
    calendar = (ROOT / "app/static/js/family-calendar.js").read_text(encoding="utf-8")
    calendar_styles = (ROOT / "app/static/css/calendar-range.css").read_text(encoding="utf-8")
    wall_styles = (ROOT / "app/static/css/wall-mode.css").read_text(encoding="utf-8")

    assert "let calendarVisibleDays = 3;" in calendar
    assert "document.body.dataset.calendarDays = String(calendarVisibleDays);" in calendar
    assert ".calendar-events.calendar-days-3" in calendar_styles
    assert "overflow-x:auto" in calendar_styles.replace(" ", "")
    assert "calendar-events.calendar-days-5" in wall_styles
    assert "calendar-events.calendar-days-7" in wall_styles
    assert "overflow-x: visible" in wall_styles
    assert "min-height:44px" in wall_styles.replace(" ", "")
    assert "@media(max-width:640px)" in wall_styles.replace(" ", "")


def test_calendar_day_selection_does_not_resize_routine_card_on_wall():
    wall_styles = (ROOT / "app/static/css/wall-mode.css").read_text(encoding="utf-8")
    compact = wall_styles.replace(" ", "").replace("\n", "")
    assert 'data-calendar-days="1"' not in compact
    assert 'data-calendar-days="3"' not in compact
    assert 'data-calendar-days="5"' not in compact
    assert 'data-calendar-days="7"' not in compact
    assert "routine-card" in compact
    assert "calendar-card" in compact
    assert "grid-template-columns:repeat(4,minmax(0,1fr))" in compact
    assert "min-width:921px" in compact
    assert "max-width:1180px" in compact


def test_render_wall_page_rejects_invalid_roles():
    for value in [None, {}, {"role": "anonymous"}, {"role": "administrator"}]:
        try:
            render_wall_page(value)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid wall role accepted")


if __name__ == "__main__":
    test_wall_route_roles_and_admin_policy()
    test_wall_reuses_family_dashboard_as_shared_display()
    test_named_wall_screens_are_stored_and_rendered()
    test_named_wall_screen_access_policy_and_missing_screen()
    test_wall_shared_display_hides_owner_technical_details()
    test_wall_family_assets_are_available()
    test_wall_mode_frontend_is_read_only_and_role_safe()
    test_uv_backend_validation_and_categories_remain_strict()
    test_wall_defaults_to_three_calendar_days_and_remains_responsive()
    test_calendar_day_selection_does_not_resize_routine_card_on_wall()
    test_render_wall_page_rejects_invalid_roles()
    print("Wall dashboard tests OK")
