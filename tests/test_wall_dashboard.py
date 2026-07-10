import tempfile
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.main_auth import app
from app.wall_view import WALL_ROLES, render_wall_page

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
    response = client.post("/api/auth/login", json={"username": username, "password": credential()})
    assert response.status_code == 200, response.text
    profile = client.get("/api/auth/me")
    assert profile.status_code == 200, profile.text
    return profile.json().get("csrf_token") or profile.json().get("csrf_value")


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
            assert 'id="wallSafetyStrip"' in page
            assert '/static/js/wall-safety.js' in page
            assert '/static/css/wall-safety-polish.css' in page
            assert '/static/js/wall.js' not in page
            assert 'class="wall-shell"' not in page
            assert 'href="/admin">Administration</a>' not in page


def test_named_wall_screens_store_visibility_options_and_render_them():
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
                "display_options": {"show_admin_link": True, "show_safety_status": False},
                "is_active": True,
            },
        )
        assert response.status_code == 200, response.text
        created = response.json()["screen"]
        assert created["url"] == "/wall/wall-stuen"
        assert created["modules"] == ["routine", "calendar", "weather"]
        assert created["display_options"] == {"show_admin_link": True, "show_safety_status": False}

        page = client.get("/wall/wall-stuen")
        assert page.status_code == 200
        assert '<title>Jarvis – Wall Stuen</title>' in page.text
        assert 'data-wall-screen-slug="wall-stuen"' in page.text
        assert 'href="/admin">Administration</a>' in page.text
        assert '#wallSafetyStrip{display:none!important}' in page.text
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
        assert client.get("/api/admin/screens").status_code == 403


def test_wall_family_assets_are_available():
    with wall_environment() as client:
        login(client, "wall_display")
        for asset, marker in [
            ("/static/js/family.js", "renderCalendar"),
            ("/static/js/family-calendar.js", "calendarDayChoices"),
            ("/static/js/routines.js", "routineEndpoints"),
            ("/static/js/wall-mode.js", "requestFullscreen"),
            ("/static/js/wall-safety.js", "/api/family/safety-status"),
            ("/static/css/wall-mode.css", ".wall-safety-strip"),
            ("/static/css/wall-safety-polish.css", ".wall-safety-item.ok"),
            ("/static/css/wall-profiles.css", 'data-wall-screen-profile="tablet"'),
            ("/static/css/wall-final-polish.css", ".family-task-lists"),
            ("/static/pictograms/routines.svg", 'symbol id="complete"'),
        ]:
            response = client.get(asset)
            assert response.status_code == 200, asset
            assert marker in response.text


def test_wall_mode_frontend_is_read_only_and_role_safe():
    javascript = (ROOT / "app/static/js/wall-mode.js").read_text(encoding="utf-8")
    view = (ROOT / "app/wall_view.py").read_text(encoding="utf-8")
    combined = javascript + view
    for forbidden in ["fetch(", "localStorage", "sessionStorage", "eval(", "innerHTML", "URLSearchParams"]:
        assert forbidden not in combined
    assert "requestFullscreen" in javascript
    assert "fullscreenchange" in javascript
    assert 'role == "owner" and screen_option(screen, "show_admin_link", False)' in view
    assert 'shared_display = {"role": "wall_display", "display_name": ""}' in view


def test_calendar_day_selection_does_not_resize_routine_card_on_wall():
    mode = (ROOT / "app/static/css/wall-mode.css").read_text(encoding="utf-8")
    profiles = (ROOT / "app/static/css/wall-profiles.css").read_text(encoding="utf-8")
    compact = (mode + profiles).replace(" ", "").replace("\n", "")

    for day_count in [1, 3, 5, 7]:
        selector = f'data-calendar-days="{day_count}"'
        assert selector not in compact
        assert f"calendar-days-{day_count}" in compact

    assert 'body[data-wall-dashboard="true"].family-grid{grid-template-columns:repeat(12,minmax(0,1fr))' in compact
    assert 'body[data-wall-dashboard="true"].routine-card{grid-column:span6' in compact
    assert 'body[data-wall-dashboard="true"].calendar-card{grid-column:span6' in compact
    assert 'data-wall-screen-profile="tablet"].family-grid{grid-template-columns:repeat(2,minmax(0,1fr))' in compact
    assert 'data-wall-screen-profile="tablet"].routine-card' in compact
    assert 'data-wall-screen-profile="tablet"].calendar-card' in compact


def test_final_wall_polish_fills_last_row_and_repairs_mobile_top_bars():
    polish = (ROOT / "app/static/css/wall-final-polish.css").read_text(encoding="utf-8")
    surface = (ROOT / "app/static/css/wall-surface.css").read_text(encoding="utf-8")
    compact = polish.replace(" ", "").replace("\n", "")

    assert '@importurl("/static/css/wall-final-polish.css")' in surface.replace(" ", "").replace("\n", "")
    assert 'data-wall-screen-slug="wall"].family-grid.family-tasks-card' in compact
    assert "grid-column:1/-1!important" in compact
    assert "grid-row:auto!important" in compact
    assert ".family-task-lists{grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr))" in compact
    assert '.family-footer{display:none!important' in compact
    assert "@media(max-width:640px)" in compact
    assert ".wall-top-bars{grid-template-columns:minmax(0,1fr)!important" in compact
    assert ".wall-top-bars.wall-safety-strip" in compact
    assert "grid-template-columns:repeat(2,minmax(0,1fr))!important" in compact
    assert ".wall-top-bars.wall-display-actions" in compact
    assert "grid-template-columns:repeat(auto-fit,minmax(105px,1fr))!important" in compact


def test_wall_safety_strip_is_bottom_scoped_and_static():
    template = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    wall_styles = (ROOT / "app/static/css/wall-mode.css").read_text(encoding="utf-8")
    wall_safety = (ROOT / "app/static/js/wall-safety.js").read_text(encoding="utf-8")
    assert 'id="wallSafetyStrip"' in template
    assert 'aria-label="Tryghedsstatus for hjemmet"' in template
    assert '/static/js/wall-safety.js' in template
    assert '/static/css/wall-safety-polish.css' in template
    for item in ["internet", "doors", "motion", "cameras"]:
        assert f'data-wall-safety-item="{item}"' in template
    assert ".wall-safety-strip {" in wall_styles
    assert 'body[data-wall-dashboard="true"] .wall-safety-strip' in wall_styles
    assert "position: sticky" in wall_styles
    assert "bottom: max" in wall_styles
    assert 'fetch("/api/family/safety-status", { credentials: "same-origin" })' in wall_safety


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
    test_named_wall_screens_store_visibility_options_and_render_them()
    test_named_wall_screen_access_policy_and_missing_screen()
    test_wall_family_assets_are_available()
    test_wall_mode_frontend_is_read_only_and_role_safe()
    test_calendar_day_selection_does_not_resize_routine_card_on_wall()
    test_final_wall_polish_fills_last_row_and_repairs_mobile_top_bars()
    test_wall_safety_strip_is_bottom_scoped_and_static()
    test_render_wall_page_rejects_invalid_roles()
    print("Wall dashboard tests OK")
