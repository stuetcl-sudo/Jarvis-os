import contextlib
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.main_auth import app


def valid_password():
    return "".join(["Local", "Test", "Pass", "-42!"])


@contextlib.contextmanager
def environment():
    previous = (config.DB_PATH, config.AUTH_COOKIE_SECURE)
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "users.db")
        config.AUTH_COOKIE_SECURE = False
        init_db()
        initialize_auth_tables()
        with TestClient(app, follow_redirects=False) as client:
            yield client
    config.DB_PATH, config.AUTH_COOKIE_SECURE = previous


def login(client, role="owner"):
    auth_service.create_user(role, role.title(), role, valid_password())
    response = client.post("/api/auth/login", json={"username": role, "password": valid_password()})
    assert response.status_code == 200
    return client.get("/api/auth/me").json()["csrf_token"]


def create(client, token, username, role, password=None, display_name="Ny bruger"):
    return client.post(
        "/api/admin/users",
        headers={"X-CSRF-Token": token},
        json={
            "username": username,
            "display_name": display_name,
            "role": role,
            "password": password if password is not None else valid_password(),
        },
    )


def test_owner_can_create_supported_users_and_only_wall_users_are_assignable():
    with environment() as client:
        token = login(client)
        for username, role in [
            ("voksen", "adult"),
            ("barn", "child"),
            ("vaeg", "wall_display"),
        ]:
            response = create(client, token, username, role)
            assert response.status_code == 201, response.text
            assert response.json()["user"]["role"] == role
            assert "password" not in response.text
            assert "hash" not in response.text

        choices = client.get("/api/admin/screens").json()["wall_users"]
        assert [user["username"] for user in choices] == ["vaeg"]


def test_non_owner_cannot_create_users():
    for role in ["adult", "child", "wall_display"]:
        with environment() as client:
            login(client, role)
            response = client.post(
                "/api/admin/users",
                headers={"X-CSRF-Token": client.get("/api/auth/me").json()["csrf_token"]},
                json={"username": "nope", "display_name": "Nej", "role": "adult", "password": valid_password()},
            )
            assert response.status_code == 403
            assert auth_service.get_user("nope") is None


def test_duplicate_invalid_role_owner_role_and_invalid_password_are_rejected():
    with environment() as client:
        token = login(client)
        assert create(client, token, "samme", "adult").status_code == 201
        duplicate = create(client, token, "SAMME", "child")
        assert duplicate.status_code == 400
        assert duplicate.json()["detail"] == "Brugernavnet findes allerede."

        for role in ["owner", "administrator", ""]:
            assert create(client, token, f"role-{role or 'empty'}", role).status_code == 400

        for invalid_password in ["for-kort", "x" * 129]:
            assert create(client, token, "weak", "adult", invalid_password).status_code == 400
        assert create(client, token, "navn", "adult", display_name="  ").status_code == 400


def test_disabled_wall_user_is_not_assignable():
    with environment() as client:
        token = login(client)
        assert create(client, token, "vaeg", "wall_display").status_code == 201
        auth_service.set_user_disabled("vaeg", True)
        choices = client.get("/api/admin/screens").json()["wall_users"]
        assert choices == []


if __name__ == "__main__":
    test_owner_can_create_supported_users_and_only_wall_users_are_assignable()
    test_non_owner_cannot_create_users()
    test_duplicate_invalid_role_owner_role_and_invalid_password_are_rejected()
    test_disabled_wall_user_is_not_assignable()
