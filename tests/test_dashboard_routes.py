import re
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.auth.service import initialize_auth_tables
from app.main_auth import app

ROOT = Path(__file__).resolve().parents[1]
TEST_DB_DIR = tempfile.TemporaryDirectory()
config.DB_PATH = str(Path(TEST_DB_DIR.name) / "dashboard.db")
initialize_auth_tables()
client = TestClient(app, follow_redirects=False)


def test_root_returns_anonymous_family_dashboard():
    response = client.get("/")
    assert response.status_code == 200
    assert "Her er et roligt overblik over hjemmet" in response.text
    assert "Ikke tilsluttet endnu" in response.text
    assert 'data-family-role="anonymous"' in response.text
    assert 'href="/login">Log ind</a>' in response.text
    assert 'href="/admin"' not in response.text
    assert 'id="routineEditButton"' not in response.text
    assert "Mission Control" not in response.text
    assert "<dt>CPU</dt>" not in response.text
    assert 'data-family-card="routine"' in response.text
    assert 'data-family-card="calendar"' in response.text
    assert 'data-family-card="weather"' in response.text
    assert "/static/js/family.js" in response.text
    assert "/static/js/routines.js" in response.text
    assert "/static/js/routine-editor.js" in response.text
    assert "/static/css/routines.css" in response.text
    assert "/static/css/routine-editor.css" in response.text
    assert "/static/css/calendar.css" in response.text
    assert "/static/css/weather.css" in response.text


def test_admin_requires_login_and_static_home_administration_is_preserved():
    response = client.get("/admin")
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/admin"
    static_admin = client.get("/static/admin.html")
    assert static_admin.status_code == 200
    for expected in [
        "Hjemmets administration",
        "Oversigt",
        "Hjemmet",
        "Funktioner",
        "Forbindelser",
        "Brugere og adgang",
        "Systemstatus",
        "Avanceret",
        "Handlinger og godkendelser",
        "Automatiske regler",
        "Docker og tekniske tjenester",
    ]:
        assert expected in static_admin.text
    assert "/static/js/admin.js" in static_admin.text


def test_login_page_and_assets_load():
    response = client.get("/login")
    assert response.status_code == 303
    assert response.headers["location"] == "/bootstrap"
    bootstrap = client.get("/bootstrap")
    assert bootstrap.status_code == 200
    assert "Velkommen til Jarvis" in bootstrap.text
    for asset in ["/static/css/login.css", "/static/js/login.js"]:
        loaded = client.get(asset)
        assert loaded.status_code == 200
        assert loaded.text.strip()


def test_family_page_contains_no_action_engine_write_controls():
    family = client.get("/").text
    normalized = family.lower()

    assert 'id="routineEditorCancel"' in family
    assert "Annuller" in family

    forbidden_action_paths = [
        "/api/actions/queue",
        "/api/actions/approve",
        "/api/actions/deny",
        "/api/actions/cancel",
        "/api/actions/request-restart",
        "/api/actions/run-check-now",
        "/api/actions/classify-container",
        "/api/actions/toggle-policy",
    ]
    forbidden_action_controls = [
        'data-action="approve"',
        'data-action="deny"',
        'data-action="cancel"',
        'data-action="request-restart"',
        'data-action="run-check-now"',
        'data-action="classify-container"',
        'data-action="toggle-policy"',
        'id="actionApprove"',
        'id="actionDeny"',
        'id="actionCancel"',
        'id="requestRestart"',
        'id="runCheckNow"',
        'id="classifyContainer"',
        'id="togglePolicy"',
    ]
    for forbidden in forbidden_action_paths + forbidden_action_controls:
        assert forbidden.lower() not in normalized

    assert not re.search(r"/api/actions/[^\"'\s]*/(?:approve|deny|cancel)(?:[\"'\s]|$)", normalized)
    assert "/api/actions/" not in normalized


def test_existing_api_routes_remain_available():
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/family/weather").status_code == 200
    assert client.get("/api/family/calendar").status_code == 200
    routines = client.get("/api/family/routines")
    assert routines.status_code == 200
    assert routines.json() == {"status": "authentication_required", "routines": []}
    assert client.get("/api/family/routines/definitions").status_code == 401
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    for expected in [
        "/api/mission", "/api/family/weather", "/api/family/calendar",
        "/api/family/routines", "/api/family/routines/definitions",
        "/api/family/routines/definitions/{routine_id}",
        "/api/family/routines/definitions/{routine_id}/reset-default",
        "/api/family/routines/{routine_id}/complete",
        "/api/family/routines/{routine_id}/back",
        "/api/family/routines/{routine_id}/reset",
        "/api/actions", "/api/actions/queue", "/api/actions/{action_id}/approve",
        "/api/worker/run-once", "/api/service-classifications/{service}",
        "/api/assets", "/api/policies/{policy_id:path}/enable", "/api/events/latest",
        "/api/auth/login", "/api/auth/me", "/api/auth/logout",
    ]:
        assert expected in paths


def test_static_css_javascript_and_pictogram_assets_load():
    for asset in [
        "/static/css/common.css", "/static/css/family.css", "/static/css/weather.css",
        "/static/css/calendar.css", "/static/css/routines.css",
        "/static/css/routine-editor.css", "/static/css/admin.css", "/static/css/login.css",
        "/static/js/family.js", "/static/js/routines.js", "/static/js/routine-editor.js",
        "/static/js/admin.js", "/static/js/admin-render.js", "/static/js/admin-page.js",
        "/static/js/login.js", "/static/pictograms/routines.svg",
        "/static/style.css",
    ]:
        response = client.get(asset)
        assert response.status_code == 200, asset
        assert response.text.strip(), asset


def test_family_javascript_keeps_existing_read_only_get_requests():
    javascript = (ROOT / "app/static/js/family.js").read_text()
    assert not re.search(r"\b(POST|PUT|PATCH|DELETE)\b", javascript, re.IGNORECASE)
    assert "method:" not in javascript
    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert "Authorization" not in javascript

    assert "async function refreshSource(url, onSuccess, onFailure)" in javascript
    helper_match = re.search(
        r'fetch\(\s*url\s*,\s*\{([^{}]*)\}\s*\)',
        javascript,
    )
    assert helper_match
    options = helper_match.group(1)
    assert re.search(r'\bcredentials\s*:\s*["\']same-origin["\']', options)
    assert not re.search(r'\bmethod\s*:', options, re.IGNORECASE)

    for endpoint in [
        "/api/mission", "/api/family/weather", "/api/family/calendar", "/api/health",
    ]:
        assert f'refreshSource("{endpoint}",' in javascript
    assert javascript.count('credentials: "same-origin"') == 1


def test_validation_script_checks_protected_live_v010_deployment():
    script = (ROOT / "scripts/validate.sh").read_text()
    helper = (ROOT / "scripts/validate_family_status.py").read_text()
    assert "docker compose up -d --build --force-recreate jarvis-os" in script
    assert 'PYTHONPATH=. "$PYTHON_BIN" tests/test_admin_ui.py' in script
    assert 'PYTHONPATH=. "$PYTHON_BIN" tests/test_family_routines.py' in script
    assert 'PYTHONPATH=. "$PYTHON_BIN" tests/test_routine_editor.py' in script
    assert 'PYTHONPATH=. "$PYTHON_BIN" tests/test_live_family_status_validation.py' in script
    assert 'PYTHONPATH=. "$PYTHON_BIN" tests/test_calendar_integration.py' in script
    assert 'PYTHONPATH=. "$PYTHON_BIN" tests/test_weather_integration.py' in script
    assert 'PYTHONPATH=. "$PYTHON_BIN" tests/test_family_role_views.py' in script
    assert 'PYTHONPATH=. "$PYTHON_BIN" tests/test_setup_state.py' in script
    assert 'check_live_route "/" "family dashboard" "Her er et roligt overblik over hjemmet"' in script
    assert 'check_live_json_status "/api/family/weather" "family weather API" "weather"' in script
    assert 'check_live_json_status "/api/family/calendar" "family calendar API" "calendar"' in script
    assert '"status":"not_configured"' not in script
    assert 'check_live_route "/api/family/routines" "family routines API" \'"status":"authentication_required"\'' in script
    assert 'check_live_login || fail "Live login route check failed."' in script
    assert 'if [ "$location" = "/bootstrap" ]' in script
    assert 'check_live_redirect "/admin" "/login?next=/admin"' in script
    assert 'check_live_route "/static/admin.html" "home administration static page" "Hjemmets administration"' in script
    assert '"weather": {"ok", "stale", "not_configured", "unavailable"}' in helper
    assert '"calendar": {"ok", "partial", "stale", "not_configured", "unavailable"}' in helper
    for asset in [
        "/static/js/login.js", "/static/js/family.js", "/static/js/routines.js",
        "/static/js/routine-editor.js", "/static/js/admin.js", "/static/js/admin-render.js",
        "/static/js/admin-page.js", "/static/css/login.css",
        "/static/css/family.css", "/static/css/weather.css", "/static/css/calendar.css",
        "/static/css/routines.css", "/static/css/routine-editor.css", "/static/css/admin.css",
        "/static/pictograms/routines.svg",
    ]:
        assert f'check_live_route "{asset}"' in script


if __name__ == "__main__":
    for test in [
        test_root_returns_anonymous_family_dashboard,
        test_admin_requires_login_and_static_home_administration_is_preserved,
        test_login_page_and_assets_load,
        test_family_page_contains_no_action_engine_write_controls,
        test_existing_api_routes_remain_available,
        test_static_css_javascript_and_pictogram_assets_load,
        test_family_javascript_keeps_existing_read_only_get_requests,
        test_validation_script_checks_protected_live_v010_deployment,
    ]:
        test()
    print("Dashboard route tests OK")
