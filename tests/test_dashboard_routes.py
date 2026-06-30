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
    assert "Mission Control" not in response.text
    assert "<dt>CPU</dt>" not in response.text
    assert 'data-family-card="weather"' in response.text
    assert "/static/js/family.js" in response.text
    assert "/static/css/weather.css" in response.text


def test_admin_requires_login_and_static_mission_control_is_preserved():
    response = client.get("/admin")
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/admin"
    static_admin = client.get("/static/admin.html")
    assert static_admin.status_code == 200
    for expected in [
        "Mission Control",
        "Action Queue",
        "Policy Engine",
        "Asset Overview",
        "Live event feed",
        "Docker status",
        "Unknown containers",
    ]:
        assert expected in static_admin.text
    assert "/static/js/admin.js" in static_admin.text


def test_login_page_and_assets_load():
    response = client.get("/login")
    assert response.status_code == 200
    assert "Log ind på Jarvis" in response.text
    assert "Ingen aktiv ejer findes endnu" in response.text
    for asset in ["/static/css/login.css", "/static/js/login.js"]:
        loaded = client.get(asset)
        assert loaded.status_code == 200
        assert loaded.text.strip()


def test_family_page_contains_no_action_engine_write_controls():
    family = client.get("/").text.lower()
    for forbidden in [
        "/api/actions/queue",
        "approve",
        "deny",
        "cancel",
        "request restart",
        "run check now",
        "classifycontainer",
        "togglepolicy",
    ]:
        assert forbidden not in family


def test_existing_api_routes_remain_available():
    assert client.get("/api/health").status_code == 200
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    for expected in [
        "/api/mission",
        "/api/family/weather",
        "/api/actions",
        "/api/actions/queue",
        "/api/actions/{action_id}/approve",
        "/api/worker/run-once",
        "/api/service-classifications/{service}",
        "/api/assets",
        "/api/policies/{policy_id:path}/enable",
        "/api/events/latest",
        "/api/auth/login",
        "/api/auth/me",
        "/api/auth/logout",
    ]:
        assert expected in paths


def test_static_css_and_javascript_assets_load():
    for asset in [
        "/static/css/common.css",
        "/static/css/family.css",
        "/static/css/weather.css",
        "/static/css/admin.css",
        "/static/css/login.css",
        "/static/js/family.js",
        "/static/js/admin.js",
        "/static/js/login.js",
        "/static/style.css",
    ]:
        response = client.get(asset)
        assert response.status_code == 200, asset
        assert response.text.strip(), asset


def test_family_javascript_uses_read_only_get_requests_only():
    javascript = (ROOT / "app/static/js/family.js").read_text()
    assert not re.search(r"\b(POST|PUT|PATCH|DELETE)\b", javascript, re.IGNORECASE)
    assert "method:" not in javascript
    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert "Authorization" not in javascript
    fetch_calls = re.findall(r'fetch\(\s*["\']([^"\']+)["\']\s*\)', javascript)
    assert fetch_calls == ["/api/mission", "/api/family/weather", "/api/health"]


def test_validation_script_checks_protected_live_v08_deployment():
    script = (ROOT / "scripts/validate.sh").read_text()
    assert "docker compose up -d --build --force-recreate jarvis-os" in script
    assert 'PYTHONPATH=. "$PYTHON_BIN" tests/test_weather_integration.py' in script
    assert 'PYTHONPATH=. "$PYTHON_BIN" tests/test_family_role_views.py' in script
    assert 'check_live_route "/" "family dashboard" "Her er et roligt overblik over hjemmet"' in script
    assert 'check_live_route "/api/family/weather" "family weather API" \'"status":"not_configured"\'' in script
    assert 'check_live_route "/login" "login page" "Log ind på Jarvis"' in script
    assert 'check_live_redirect "/admin" "/login?next=/admin"' in script
    assert 'check_live_route "/static/admin.html" "Mission Control static page" "Mission Control"' in script
    for asset in [
        "/static/js/login.js",
        "/static/js/family.js",
        "/static/js/admin.js",
        "/static/css/login.css",
        "/static/css/family.css",
        "/static/css/weather.css",
        "/static/css/admin.css",
    ]:
        assert f'check_live_route "{asset}"' in script


if __name__ == "__main__":
    for test in [
        test_root_returns_anonymous_family_dashboard,
        test_admin_requires_login_and_static_mission_control_is_preserved,
        test_login_page_and_assets_load,
        test_family_page_contains_no_action_engine_write_controls,
        test_existing_api_routes_remain_available,
        test_static_css_and_javascript_assets_load,
        test_family_javascript_uses_read_only_get_requests_only,
        test_validation_script_checks_protected_live_v08_deployment,
    ]:
        test()
    print("Dashboard route tests OK")
