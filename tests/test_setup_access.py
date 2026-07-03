import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.main_auth import app


PASSWORD = "LocalTestPass-42!"


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
        auth_service.create_user(f"setup-{role}", f"Setup {role}", role, PASSWORD)
        response = client.post(
            "/api/auth/login",
            json={"username": f"setup-{role}", "password": PASSWORD},
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


def test():
    test_anonymous_setup_access_is_rejected()
    test_family_roles_cannot_access_setup()
    test_owner_write_requires_csrf()
    print("Setup access tests OK")


if __name__ == "__main__":
    test()
