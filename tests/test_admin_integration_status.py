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
from app.home_assistant import HomeAssistantUnavailable


ROOT = Path(__file__).resolve().parents[1]
CHECKED = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


class ProbeClient:
    def __init__(self, response=None, error=None, requests=None, **_kwargs):
        self.response = response
        self.error = error
        self.requests = requests if requests is not None else []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, url):
        self.requests.append(url)
        if self.error:
            raise self.error
        return self.response


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
    with patch("app.integration_status.home_entity_settings.load_entity_settings", return_value={"electricity_price_entity": "sensor.price"}), patch("app.integration_status.load_home_assistant_connection", return_value=object()), patch("app.integration_status.HomeAssistantClient") as client_type:
        client_type.return_value.get_json.return_value = {"state": "1.25"}
        electricity = status_service._electricity_prices(checked, connected)
    assert electricity["state"] == "healthy"
    assert electricity["summary"] == "Strømpriser er klar"

    with patch("app.integration_status.get_health", return_value={"status": "ok", "warnings": []}):
        jarvis = status_service._jarvis(checked)
    assert jarvis["state"] == "healthy"
    assert jarvis["summary"] == "Jarvis kører normalt"


def test_home_assistant_probe_classes_are_safe():
    checked = CHECKED.isoformat()
    connection = object()
    private = "token-and-private-diagnostic"
    with patch("app.integration_status.load_home_assistant_connection", return_value=connection), patch("app.integration_status.HomeAssistantClient") as client_type:
        client_type.return_value.get_json.return_value = {"message": "API running."}
        assert status_service._home_assistant(checked)["state"] == "connected"
        client_type.return_value.get_json.side_effect = HomeAssistantUnavailable(private, "authentication")
        auth = status_service._home_assistant(checked)
        assert auth["state"] == "degraded"
        assert auth["summary"] == "Home Assistant-login kræver opmærksomhed"
        client_type.return_value.get_json.side_effect = HomeAssistantUnavailable(private, "transport")
        transport = status_service._home_assistant(checked)
        assert transport["state"] == "unavailable"
    assert private not in repr(auth) + repr(transport)


def test_scrypted_response_mapping_and_privacy():
    checked = CHECKED.isoformat()
    private_url = "https://scrypted.example/private-path"
    private_body = "private-response-body"

    def result(status_code, headers=None):
        response = type("Response", (), {
            "status_code": status_code,
            "is_redirect": 300 <= status_code < 400,
            "text": private_body,
        })()
        requests = []
        with patch.dict(os.environ, {"SCRYPTED_URL": private_url}), patch("app.integration_status.httpx.Client", side_effect=lambda **kwargs: ProbeClient(response=response, requests=requests, **kwargs)) as client_type:
            value = status_service._scrypted(checked)
        assert client_type.call_args.kwargs["follow_redirects"] is False
        assert requests == [private_url + "/"]
        assert private_url not in repr(value) and private_body not in repr(value)
        return value

    assert result(200)["state"] == "connected"
    for code in (401, 403):
        value = result(code)
        assert value["state"] == "degraded" and value["summary"] == "Scrypted-login kræver opmærksomhed"
    assert result(404)["state"] == "degraded"
    assert result(429)["state"] == "degraded"
    assert result(503)["state"] == "unavailable"
    assert result(302)["state"] == "degraded"

    with patch.dict(os.environ, {"SCRYPTED_URL": private_url}), patch("app.integration_status.httpx.Client", side_effect=lambda **kwargs: ProbeClient(error=status_service.httpx.ConnectError("private"), **kwargs)):
        assert status_service._scrypted(checked)["state"] == "unavailable"
    with patch.dict(os.environ, {"SCRYPTED_URL": "https://user:private@scrypted.example"}):
        invalid = status_service._scrypted(checked)
    assert invalid["state"] == "degraded" and "user" not in repr(invalid) and "private" not in repr(invalid)


def test_electricity_entity_probe_mapping_and_privacy():
    checked = CHECKED.isoformat()
    connected = {"state": "connected"}
    private_entity = "sensor.private_price"

    def probe(result=None, error=None):
        with patch("app.integration_status.home_entity_settings.load_entity_settings", return_value={"electricity_price_entity": private_entity}), patch("app.integration_status.load_home_assistant_connection", return_value=object()), patch("app.integration_status.HomeAssistantClient") as client_type:
            client_type.return_value.get_json.return_value = result
            client_type.return_value.get_json.side_effect = error
            value = status_service._electricity_prices(checked, connected)
        assert private_entity not in repr(value)
        return value

    assert probe({"state": "1.25"})["state"] == "healthy"
    for state in ("unknown", "unavailable"):
        assert probe({"state": state})["state"] == "degraded"
    assert probe(error=HomeAssistantUnavailable(response_class="not_found"))["state"] == "degraded"
    assert probe(error=HomeAssistantUnavailable(response_class="transport"))["state"] == "unavailable"
    with patch("app.integration_status.home_entity_settings.load_entity_settings", return_value={"electricity_price_entity": private_entity}):
        outage = status_service._electricity_prices(checked, {"state": "unavailable"})
    assert outage["state"] == "unavailable" and private_entity not in repr(outage)


def test_jarvis_degraded_mappings():
    checked = CHECKED.isoformat()
    with patch("app.integration_status.get_health", return_value={"status": "ok", "warnings": ["private warning"]}):
        warning = status_service._jarvis(checked)
    assert warning["state"] == "degraded" and warning["technical_detail"]["warning_count"] == 1
    assert "private warning" not in repr(warning)
    with patch("app.integration_status.get_health", return_value={"status": "critical", "warnings": []}):
        assert status_service._jarvis(checked)["state"] == "degraded"
    with patch("app.integration_status.get_health", side_effect=RuntimeError("private")):
        failed = status_service._jarvis(checked)
    assert failed["state"] == "degraded" and "private" not in repr(failed)


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
    test_home_assistant_probe_classes_are_safe()
    test_scrypted_response_mapping_and_privacy()
    test_electricity_entity_probe_mapping_and_privacy()
    test_jarvis_degraded_mappings()
    test_contract_and_technical_detail_allowlist()
    test_admin_frontend_contract()
    print("Admin integration status tests OK")


if __name__ == "__main__":
    test()
