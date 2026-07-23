import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import config, home_setup, settings_store
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.main_auth import app
from app.setup_state import setup_status


TEST_LOGIN_VALUE = "example-login-value-42!"


@contextmanager
def environment():
    previous_path = config.DB_PATH
    previous_secure = config.AUTH_COOKIE_SECURE
    with tempfile.TemporaryDirectory() as folder, patch.dict(
        os.environ,
        {
            "CONFIG_MASTER_KEY": "example-master-key",
            "HOME_ASSISTANT_URL": "",
            "HOME_ASSISTANT_TOKEN": "",
        },
    ):
        config.DB_PATH = str(Path(folder) / "setup-state.db")
        config.AUTH_COOKIE_SECURE = False
        init_db()
        initialize_auth_tables()
        with TestClient(app, follow_redirects=False) as client:
            yield client
        config.DB_PATH = previous_path
        config.AUTH_COOKIE_SECURE = previous_secure


def create_owner(disabled=False):
    auth_service.create_user("owner", "Owner", "owner", TEST_LOGIN_VALUE)
    if disabled:
        auth_service.set_user_disabled("owner", True)


def login_owner(client):
    response = client.post(
        "/api/auth/login", json={"username": "owner", "password": TEST_LOGIN_VALUE}
    )
    assert response.status_code == 200, response.text


def complete_basic_setup():
    home_setup.save_home_settings(
        "My home", "Europe/Copenhagen", "Owner", db_path=config.DB_PATH
    )
    home_setup.complete_setup(db_path=config.DB_PATH)


def configure_valid_home_assistant():
    settings_store.set_setting(
        "home_assistant.base_url", "http://homeassistant.example.com:8123", db_path=config.DB_PATH
    )
    settings_store.set_secret(
        "home_assistant.token", "example-token", db_path=config.DB_PATH
    )


def test_authoritative_states_and_existing_configuration():
    with environment():
        assert setup_status()["state"] == "bootstrap_required"
        create_owner()
        assert setup_status()["state"] == "owner_created"
        complete_basic_setup()
        assert setup_status()["state"] == "home_assistant_required"
        configure_valid_home_assistant()
        status = setup_status()
        assert status["state"] == "ready"
        assert status["ready"] is True


def test_disabled_owner_does_not_reopen_bootstrap():
    with environment() as client:
        create_owner(disabled=True)
        assert setup_status()["state"] == "owner_created"
        assert client.get("/api/bootstrap/status").json()["bootstrap_required"] is False
        response = client.get("/bootstrap")
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_owner_status_api_and_deterministic_page_redirects():
    with environment() as client:
        assert client.get("/login").headers["location"] == "/bootstrap"
        assert client.get("/setup").headers["location"] == "/login?next=/setup"
        assert client.get("/admin").headers["location"] == "/login?next=/admin"
        assert client.get("/api/admin/setup/status").status_code == 401
        public_status = client.get("/api/bootstrap/status")
        assert public_status.status_code == 200
        assert public_status.json()["bootstrap_required"] is True

        create_owner()
        assert client.get("/bootstrap").headers["location"] == "/login"
        login_owner(client)
        status = client.get("/api/admin/setup/status")
        assert status.status_code == 200
        assert status.json()["state"] == "owner_created"
        assert client.get("/admin").headers["location"] == "/setup"
        assert client.get("/setup").status_code == 200

        complete_basic_setup()
        assert client.get("/admin").headers["location"] == "/setup"
        configure_valid_home_assistant()
        assert client.get("/admin").status_code == 200
        assert client.get("/setup").headers["location"] == "/admin"

    with environment() as client:
        create_owner()
        auth_service.create_user("adult", "Adult", "adult", TEST_LOGIN_VALUE)
        response = client.post(
            "/api/auth/login", json={"username": "adult", "password": TEST_LOGIN_VALUE}
        )
        assert response.status_code == 200
        assert client.get("/api/admin/setup/status").status_code == 403


def test_no_login_bootstrap_setup_redirect_loop():
    with environment() as client:
        first = client.get("/login")
        assert first.headers["location"] == "/bootstrap"
        assert client.get(first.headers["location"]).status_code == 200

        create_owner()
        assert client.get("/login").status_code == 200
        assert client.get("/bootstrap").headers["location"] == "/login"
        assert client.get("/setup").headers["location"] == "/login?next=/setup"


def test():
    test_authoritative_states_and_existing_configuration()
    test_disabled_owner_does_not_reopen_bootstrap()
    test_owner_status_api_and_deterministic_page_redirects()
    test_no_login_bootstrap_setup_redirect_loop()
    print("Setup state tests OK")


if __name__ == "__main__":
    test()
