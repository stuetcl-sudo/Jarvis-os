import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_root_returns_family_dashboard():
    response = client.get("/")
    assert response.status_code == 200
    assert "Her er et roligt overblik over hjemmet" in response.text
    assert "Ikke tilsluttet endnu" in response.text
    assert 'href="/admin"' in response.text
    assert "/static/js/family.js" in response.text


def test_admin_returns_mission_control():
    response = client.get("/admin")
    assert response.status_code == 200
    for expected in [
        "Action Queue",
        "Policy Engine",
        "Asset Overview",
        "Live event feed",
        "Docker status",
        "Unknown containers",
    ]:
        assert expected in response.text
    assert "/static/js/admin.js" in response.text


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
        "/api/actions",
        "/api/actions/queue",
        "/api/actions/{action_id}/approve",
        "/api/worker/run-once",
        "/api/service-classifications/{service}",
        "/api/assets",
        "/api/policies/{policy_id:path}/enable",
        "/api/events/latest",
    ]:
        assert expected in paths


def test_static_css_and_javascript_assets_load():
    for asset in [
        "/static/css/common.css",
        "/static/css/family.css",
        "/static/css/admin.css",
        "/static/js/family.js",
        "/static/js/admin.js",
        "/static/style.css",
    ]:
        response = client.get(asset)
        assert response.status_code == 200, asset
        assert response.text.strip(), asset


def test_family_javascript_uses_read_only_get_requests_only():
    javascript = (ROOT / "app/static/js/family.js").read_text()
    assert not re.search(r"\b(POST|PUT|PATCH|DELETE)\b", javascript, re.IGNORECASE)
    assert "method:" not in javascript
    fetch_calls = re.findall(r'fetch\(\s*["\']([^"\']+)["\']\s*\)', javascript)
    assert fetch_calls == ["/api/health", "/api/mission"]


def test_validation_script_checks_live_v08_deployment():
    script = (ROOT / "scripts/validate.sh").read_text()
    assert "docker compose up -d --build --force-recreate jarvis-os" in script
    assert 'check_live_route "/" "family dashboard" "Her er et roligt overblik over hjemmet"' in script
    assert 'check_live_route "/admin" "Mission Control" "Mission Control"' in script
    for asset in [
        "/static/js/family.js",
        "/static/js/admin.js",
        "/static/css/family.css",
        "/static/css/admin.css",
    ]:
        assert f'check_live_route "{asset}"' in script


if __name__ == "__main__":
    for test in [
        test_root_returns_family_dashboard,
        test_admin_returns_mission_control,
        test_family_page_contains_no_action_engine_write_controls,
        test_existing_api_routes_remain_available,
        test_static_css_and_javascript_assets_load,
        test_family_javascript_uses_read_only_get_requests_only,
        test_validation_script_checks_live_v08_deployment,
    ]:
        test()
    print("Dashboard route tests OK")
