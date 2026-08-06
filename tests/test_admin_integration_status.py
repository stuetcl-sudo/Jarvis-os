import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import config, integration_status as status_service
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.main_auth import app


ROOT = Path(__file__).resolve().parents[1]
CHECKED = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def credential():
    return "".join(["Integration", "Status", "Pass", "-42!"])


def client_for(role):
    folder = tempfile.TemporaryDirectory()
    previous = config.DB_PATH
    config.DB_PATH = str(Path(folder.name) / "status.db")
    init_db()
    initialize_auth_tables()
    client = TestClient(app, follow_redirects=False)
    auth_service.create_user(f"status-{role}", f"Status {role}", role, credential())
    response = client.post("/api/auth/login", json={"username": f"status-{role}", "password": credential()})
    assert response.status_code == 200
    return folder, previous, client


def cleanup(values):
    folder, previous, client = values
    client.close()
    config.DB_PATH = previous
    folder.cleanup()


def safe_payload():
    checked = CHECKED.isoformat()
    return {"checked_at": checked, "integrations": [
        status_service._item("home_assistant", "Home Assistant", "connected", "Home Assistant er forbundet", checked),
        status_service._item("scrypted", "Scrypted", "not_configured", "Scrypted er ikke konfigureret", checked),
        status_service._item("electricity_prices", "Strømpriser", "healthy", "Strømpriser er klar", checked),
        status_service._item("jarvis", "Jarvis", "healthy", "Jarvis kører normalt", checked),
    ]}


def test_owner_only_api_access():
    with patch("app.integration_status_routes.integration_status", side_effect=safe_payload):
        owner = client_for("owner")
        try:
            response = owner[2].get("/api/admin/integrations/status")
            assert response.status_code == 200
            assert len(response.json()["integrations"]) == 4
        finally:
            cleanup(owner)
        for role in ("adult", "child", "wall_display"):
            values = client_for(role)
            try:
                assert values[2].get("/api/admin/integrations/status").status_code == 403
            finally:
                cleanup(values)


def test_safe_state_mapping_and_failures():
    checked = CHECKED.isoformat()
    with patch("app.integration_status.load_home_assistant_connection", return_value=None):
        missing = status_service._home_assistant(checked)
    assert missing["state"] == "not_configured"
    assert missing["summary"] == "Home Assistant er ikke konfigureret"

    private = "private-token-value"
    with patch("app.integration_status.load_home_assistant_connection", side_effect=RuntimeError(private)):
        failed = status_service._home_assistant(checked)
    assert failed["state"] == "unavailable"
    assert failed["summary"] == "Home Assistant svarer ikke"
    assert private not in repr(failed)

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("SCRYPTED_URL", None)
        scrypted = status_service._scrypted(checked)
    assert scrypted["state"] == "not_configured"
    assert scrypted["summary"] == "Scrypted er ikke konfigureret"

    connected = {"state": "connected"}
    with patch("app.integration_status.home_entity_settings.load_entity_settings", return_value={"electricity_price_entity": "sensor.price"}):
        electricity = status_service._electricity_prices(checked, connected)
    assert electricity["state"] == "healthy"
    assert electricity["summary"] == "Strømpriser er klar"

    with patch("app.integration_status.get_health", return_value={"status": "ok", "warnings": []}):
        jarvis = status_service._jarvis(checked)
    assert jarvis["state"] == "healthy"
    assert jarvis["summary"] == "Jarvis kører normalt"


def test_contract_and_technical_detail_allowlist():
    payload = safe_payload()
    expected_keys = {"home_assistant", "scrypted", "electricity_prices", "jarvis"}
    assert {item["key"] for item in payload["integrations"]} == expected_keys
    for item in payload["integrations"]:
        assert item["state"] in status_service.ALLOWED_STATES
        datetime.fromisoformat(item["last_checked"])
        assert set(item) == {"key", "display_name", "state", "summary", "last_checked", "technical_detail"}
    filtered = status_service._item("jarvis", "Jarvis", "healthy", "Jarvis kører normalt", CHECKED.isoformat(), {"check": "health", "url": "private", "token": "private"})
    assert filtered["technical_detail"] == {"check": "health"}
    assert "private" not in repr(filtered)

    private = "unexpected-private-diagnostic"
    with patch("app.integration_status._home_assistant", side_effect=Exception(private)):
        fallback = status_service.integration_status(now=CHECKED)
    assert fallback["integrations"][0]["state"] == "unavailable"
    assert private not in repr(fallback)


def test_admin_frontend_contract():
    html = (ROOT / "app/static/admin.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/js/admin-connections.js").read_text(encoding="utf-8")
    combined = html + javascript
    assert 'id="integrationStatusCards"' in html
    for label in ("Home Assistant", "Scrypted", "Strømpriser", "Jarvis"):
        assert label in combined
    assert 'getJson("/api/admin/integrations/status")' in javascript
    assert "Vis tekniske detaljer" in javascript
    assert "Sidst opdateret" in javascript
    for forbidden in ("innerHTML", "insertAdjacentHTML", "onclick=", "onchange=", "eval("):
        assert forbidden not in javascript


def test():
    test_owner_only_api_access()
    test_safe_state_mapping_and_failures()
    test_contract_and_technical_detail_allowlist()
    test_admin_frontend_contract()
    print("Admin integration status tests OK")


if __name__ == "__main__":
    test()
