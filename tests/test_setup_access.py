import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import config, home_assistant_setup, home_setup, managed_home_assistant_installer, settings_store
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.main_auth import app


def password():
    return "".join(["Local", "Test", "Pass", "-42!"])


def build_client(role=None):
    folder = tempfile.TemporaryDirectory()
    previous_path = config.DB_PATH
    previous_secure = config.AUTH_COOKIE_SECURE
    config.DB_PATH = str(Path(folder.name) / "access.db")
    config.AUTH_COOKIE_SECURE = False
    init_db()
    initialize_auth_tables()
    client = TestClient(app, follow_redirects=False)
    user = None
    if role:
        auth_service.create_user(f"setup-{role}", f"Setup {role}", role, password())
        response = client.post(
            "/api/auth/login",
            json={"username": f"setup-{role}", "password": password()},
        )
        assert response.status_code == 200
        user = client.get("/api/auth/me").json()
    return folder, previous_path, previous_secure, client, user


def cleanup(folder, previous_path, previous_secure, client):
    client.close()
    config.DB_PATH = previous_path
    config.AUTH_COOKIE_SECURE = previous_secure
    folder.cleanup()


def home_payload():
    return {
        "home_name": "Mit hjem",
        "timezone": "Europe/Copenhagen",
        "owner_name": "Ejer",
    }


def test_anonymous_setup_access_is_rejected():
    values = build_client()
    folder, previous_path, previous_secure, client, _user = values
    try:
        assert client.get("/api/admin/setup/home").status_code == 401
        assert client.post("/api/admin/setup/home", json=home_payload()).status_code == 401
    finally:
        cleanup(folder, previous_path, previous_secure, client)


def test_family_roles_cannot_access_setup():
    for role in ("adult", "child", "wall_display"):
        values = build_client(role)
        folder, previous_path, previous_secure, client, user = values
        try:
            assert client.get("/api/admin/setup/home").status_code == 403
            response = client.post(
                "/api/admin/setup/home",
                headers={"X-CSRF-Token": user["csrf_token"]},
                json=home_payload(),
            )
            assert response.status_code == 403
        finally:
            cleanup(folder, previous_path, previous_secure, client)


def test_owner_write_requires_csrf():
    values = build_client("owner")
    folder, previous_path, previous_secure, client, user = values
    try:
        assert client.get("/api/admin/setup/home").status_code == 200
        assert client.post("/api/admin/setup/home", json=home_payload()).status_code == 403
        response = client.post(
            "/api/admin/setup/home",
            headers={"X-CSRF-Token": user["csrf_token"]},
            json=home_payload(),
        )
        assert response.status_code == 200
        assert response.json()["home_name"] == "Mit hjem"
    finally:
        cleanup(folder, previous_path, previous_secure, client)


def ha_payload(token="example-browser-token", base_url="http://home-assistant.example.com:8123"):
    return {"base_url": base_url, "token": token}


def test_home_assistant_endpoints_are_owner_only_and_require_csrf():
    for role, expected in ((None, 401), ("adult", 403)):
        values = build_client(role)
        folder, previous_path, previous_secure, client, user = values
        try:
            headers = {"X-CSRF-Token": user["csrf_token"]} if user else {}
            assert client.get("/api/admin/setup/home-assistant").status_code == expected
            assert client.post(
                "/api/admin/setup/home-assistant/test", headers=headers, json=ha_payload()
            ).status_code == expected
            assert client.post(
                "/api/admin/setup/home-assistant/save", headers=headers, json=ha_payload()
            ).status_code == expected
        finally:
            cleanup(folder, previous_path, previous_secure, client)

    values = build_client("owner")
    folder, previous_path, previous_secure, client, _user = values
    try:
        assert client.post("/api/admin/setup/home-assistant/test", json=ha_payload()).status_code == 403
        assert client.post("/api/admin/setup/home-assistant/save", json=ha_payload()).status_code == 403
    finally:
        cleanup(folder, previous_path, previous_secure, client)


def test_home_assistant_api_errors_are_stable_safe_and_do_not_overwrite():
    values = build_client("owner")
    folder, previous_path, previous_secure, client, user = values
    headers = {"X-CSRF-Token": user["csrf_token"]}
    previous_master_key = os.environ.get("CONFIG_MASTER_KEY")
    os.environ["CONFIG_MASTER_KEY"] = "setup-access-test-key"
    try:
        with patch(
            "app.setup_routes.home_assistant_setup.test_connection",
            side_effect=home_assistant_setup.HomeAssistantSetupError(
                "unreachable", "Home Assistant-adressen kan ikke nås", 502
            ),
        ):
            response = client.post(
                "/api/admin/setup/home-assistant/test", headers=headers, json=ha_payload("new-secret")
            )
        assert response.status_code == 502
        assert settings_store.get_setting("home_assistant.base_url", "", db_path=config.DB_PATH) == ""
        assert settings_store.has_secret("home_assistant.token", db_path=config.DB_PATH) is False

        with patch(
            "app.setup_routes.managed_home_assistant_installer.managed_install_status",
            side_effect=RuntimeError("private diagnostic"),
        ):
            unavailable = client.get("/api/admin/setup/home-assistant/managed")
        assert unavailable.status_code == 500
        assert unavailable.json()["detail"]["code"] == "managed_install_status_unavailable"
        assert "private diagnostic" not in unavailable.text

        with patch(
            "app.setup_routes.managed_home_assistant_installer.request_install_plan",
            side_effect=RuntimeError("private diagnostic"),
        ):
            unavailable = client.post(
                "/api/admin/setup/home-assistant/managed/plan", headers=headers, json={}
            )
        assert unavailable.status_code == 500
        assert unavailable.json()["detail"]["code"] == "managed_install_plan_unavailable"
        assert "private diagnostic" not in unavailable.text

        settings_store.set_home_assistant_connection(
            "http://previous.example:8123", "previous-token", db_path=config.DB_PATH
        )
        response = client.post(
            "/api/admin/setup/home-assistant/save",
            headers=headers,
            json=ha_payload("new-secret", "file:///etc/passwd"),
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "unsupported_scheme"
        assert "new-secret" not in response.text
        assert settings_store.get_setting("home_assistant.base_url", db_path=config.DB_PATH) == "http://previous.example:8123"
        assert settings_store.get_secret("home_assistant.token", db_path=config.DB_PATH) == "previous-token"

        response = client.post(
            "/api/admin/setup/home-assistant/test",
            headers=headers,
            json={"base_url": "http://home-assistant.example.com", "token": ["must-not-echo"]},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "token_invalid"
        assert "must-not-echo" not in response.text

        response = client.post(
            "/api/admin/setup/home-assistant/test",
            headers=headers,
            json=["must-not-echo"],
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "malformed_request"
        assert "must-not-echo" not in response.text

        with patch(
            "app.setup_routes.home_assistant_setup.test_connection",
            side_effect=home_assistant_setup.HomeAssistantSetupError(
                "unreachable", "Home Assistant-adressen kan ikke nås", 502
            ),
        ):
            response = client.post(
                "/api/admin/setup/home-assistant/save", headers=headers, json=ha_payload("new-secret")
            )
        assert response.status_code == 502
        assert response.json()["detail"] == {
            "code": "unreachable",
            "message": "Home Assistant-adressen kan ikke nås",
        }
        assert "new-secret" not in response.text
        assert settings_store.get_secret("home_assistant.token", db_path=config.DB_PATH) == "previous-token"
        assert settings_store.get_setting("home_assistant.base_url", db_path=config.DB_PATH) == "http://previous.example:8123"

        stable_errors = (
            ("timeout", "Home Assistant svarede ikke inden for tidsgrænsen", 504),
            ("authentication_failed", "Home Assistant afviste adgangstokenet", 401),
            ("invalid_response", "Home Assistant returnerede et ugyldigt svar", 502),
            ("malformed_url", "Home Assistant-adressen er ugyldig", 400),
        )
        for code, message, status_code in stable_errors:
            with patch(
                "app.setup_routes.home_assistant_setup.test_connection",
                side_effect=home_assistant_setup.HomeAssistantSetupError(code, message, status_code),
            ):
                response = client.post(
                    "/api/admin/setup/home-assistant/test",
                    headers=headers,
                    json=ha_payload("new-secret"),
                )
            assert response.status_code == status_code
            assert response.json()["detail"] == {"code": code, "message": message}
            assert "new-secret" not in response.text
    finally:
        if previous_master_key is None:
            os.environ.pop("CONFIG_MASTER_KEY", None)
        else:
            os.environ["CONFIG_MASTER_KEY"] = previous_master_key
        cleanup(folder, previous_path, previous_secure, client)


def test_valid_save_is_secret_free_persists_and_makes_setup_ready():
    values = build_client("owner")
    folder, previous_path, previous_secure, client, user = values
    headers = {"X-CSRF-Token": user["csrf_token"]}
    token = "".join(["example", "-response-probe"])
    previous_master_key = os.environ.get("CONFIG_MASTER_KEY")
    os.environ["CONFIG_MASTER_KEY"] = "setup-access-test-key"
    try:
        home_setup.save_home_settings("Mit hjem", "Europe/Copenhagen", "Ejer", db_path=config.DB_PATH)
        home_setup.complete_setup(db_path=config.DB_PATH)
        with patch(
            "app.setup_routes.home_assistant_setup.test_connection",
            return_value={"connected": True, "code": "connected", "message": "Forbindelsen til Home Assistant virker"},
        ):
            response = client.post(
                "/api/admin/setup/home-assistant/save",
                headers=headers,
                json=ha_payload(token, "HTTP://HOME-ASSISTANT.EXAMPLE.COM:8123/"),
            )
        assert response.status_code == 200, response.text
        assert token not in response.text
        assert response.json()["setup"]["state"] == "ready"
        assert settings_store.get_setting("home_assistant.base_url", db_path=config.DB_PATH) == "http://home-assistant.example.com:8123"
        assert settings_store.get_secret("home_assistant.token", db_path=config.DB_PATH) == token
        status = client.get("/api/admin/setup/home-assistant")
        assert status.status_code == 200
        assert token not in status.text
        assert status.json()["token_configured"] is True
        conn = sqlite3.connect(config.DB_PATH)
        logged = "\n".join(
            str(value or "")
            for row in conn.execute("SELECT action, target, status, reason FROM action_log")
            for value in row
        )
        conn.close()
        assert token not in logged
    finally:
        if previous_master_key is None:
            os.environ.pop("CONFIG_MASTER_KEY", None)
        else:
            os.environ["CONFIG_MASTER_KEY"] = previous_master_key
        cleanup(folder, previous_path, previous_secure, client)


def test_managed_install_plan_access_csrf_fixed_values_and_setup_state():
    for role, expected in ((None, 401), ("adult", 403)):
        values = build_client(role)
        folder, previous_path, previous_secure, client, user = values
        try:
            headers = {"X-CSRF-Token": user["csrf_token"]} if user else {}
            assert client.get("/api/admin/setup/home-assistant/managed").status_code == expected
            assert client.post(
                "/api/admin/setup/home-assistant/managed/plan", headers=headers, json={}
            ).status_code == expected
            assert client.post(
                "/api/admin/setup/home-assistant/managed/install-request", headers=headers, json={}
            ).status_code == expected
        finally:
            cleanup(folder, previous_path, previous_secure, client)

    values = build_client("owner")
    folder, previous_path, previous_secure, client, user = values
    headers = {"X-CSRF-Token": user["csrf_token"]}
    try:
        home_setup.save_home_settings("Mit hjem", "Europe/Copenhagen", "Ejer", db_path=config.DB_PATH)
        home_setup.complete_setup(db_path=config.DB_PATH)
        assert client.get("/api/admin/setup/status").json()["state"] == "home_assistant_required"
        assert client.post("/api/admin/setup/home-assistant/managed/plan", json={}).status_code == 403
        assert client.post(
            "/api/admin/setup/home-assistant/managed/install-request", json={}
        ).status_code == 403

        no_plan = client.post(
            "/api/admin/setup/home-assistant/managed/install-request", headers=headers, json={}
        )
        assert no_plan.status_code == 409
        assert no_plan.json()["detail"]["code"] == "plan_not_ready"

        first = client.post(
            "/api/admin/setup/home-assistant/managed/plan", headers=headers, json={}
        )
        second = client.post(
            "/api/admin/setup/home-assistant/managed/plan", headers=headers, json={}
        )
        assert first.status_code == 200
        assert first.json() == second.json()
        assert first.json()["state"] == "ready_to_install"
        assert first.json()["installation_started"] is False
        assert first.json()["container_name"] == managed_home_assistant_installer.CONTAINER_NAME
        assert first.json()["volume_name"] == managed_home_assistant_installer.VOLUME_NAME
        assert first.json()["network_name"] == managed_home_assistant_installer.NETWORK_NAME
        assert first.json()["published_port"] == managed_home_assistant_installer.PUBLISHED_PORT

        requested = client.post(
            "/api/admin/setup/home-assistant/managed/install-request", headers=headers, json={}
        )
        assert requested.status_code == 200
        assert requested.json()["installation_requested"] is True
        assert "request_token" not in requested.json()
        assert all("docker.sock" not in str(value) for value in requested.json().values())
        duplicate = client.post(
            "/api/admin/setup/home-assistant/managed/install-request", headers=headers, json={}
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["code"] == "installation_already_requested"
        override_request = client.post(
            "/api/admin/setup/home-assistant/managed/install-request",
            headers=headers,
            json={"image": "example/image:latest"},
        )
        assert override_request.status_code == 400
        assert override_request.json()["detail"]["code"] == "managed_install_options_not_allowed"

        override = client.post(
            "/api/admin/setup/home-assistant/managed/plan",
            headers=headers,
            json={"image": "example/image:latest", "command": "example-command"},
        )
        assert override.status_code == 400
        assert override.json()["detail"]["code"] == "managed_install_options_not_allowed"
        assert client.get("/api/admin/setup/status").json()["state"] == "home_assistant_required"
        assert settings_store.get_setting("home_assistant.base_url", "", db_path=config.DB_PATH) == ""
        assert settings_store.has_secret("home_assistant.token", db_path=config.DB_PATH) is False
    finally:
        cleanup(folder, previous_path, previous_secure, client)


def test():
    test_anonymous_setup_access_is_rejected()
    test_family_roles_cannot_access_setup()
    test_owner_write_requires_csrf()
    test_home_assistant_endpoints_are_owner_only_and_require_csrf()
    test_home_assistant_api_errors_are_stable_safe_and_do_not_overwrite()
    test_valid_save_is_secret_free_persists_and_makes_setup_ready()
    test_managed_install_plan_access_csrf_fixed_values_and_setup_state()
    print("Setup access tests OK")


if __name__ == "__main__":
    test()
