import contextlib
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.auth.service import auth_service, initialize_auth_tables
from app.db import connect, init_db
from app.family_people import list_family_people
from app.family_task_assignments import FamilyTaskAssignmentStore
from app.main_auth import app
from app.routine_definitions import definition_to_dict
from app.routines import definition_store, routine_store
from app.screen_registry import ensure_screen_table


def valid_password():
    return "".join(["Local", "Test", "Pass", "-42!"])


@contextlib.contextmanager
def environment():
    previous = (config.DB_PATH, config.AUTH_COOKIE_SECURE, routine_store.path, definition_store.path)
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "users.db")
        config.AUTH_COOKIE_SECURE = False
        routine_store.path = Path(folder) / "routines.json"
        definition_store.path = Path(folder) / "routine-definitions.json"
        init_db()
        initialize_auth_tables()
        with TestClient(app, follow_redirects=False) as client:
            yield client
    config.DB_PATH, config.AUTH_COOKIE_SECURE, routine_store.path, definition_store.path = previous


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


def test_owner_manages_profile_with_bounded_colors_and_family_visibility():
    with environment() as client:
        token = login(client)
        created = create(client, token, "voksen", "adult").json()["user"]
        assert created["display_color"] == "teal"
        assert created["family_visible"] is True
        assert [person["user_id"] for person in list_family_people()] == [created["user_id"]]

        updated = client.put(
            f"/api/admin/users/{created['user_id']}/profile",
            headers={"X-CSRF-Token": token},
            json={"display_color": "orange", "family_visible": False},
        )
        assert updated.status_code == 200
        assert updated.json()["user"]["display_color"] == "orange"
        assert updated.json()["user"]["family_visible"] is False
        assert list_family_people() == []
        with TestClient(app, follow_redirects=False) as hidden_client:
            assert hidden_client.post(
                "/api/auth/login", json={"username": "voksen", "password": valid_password()}
            ).status_code == 200
        assert client.put(
            f"/api/admin/users/{created['user_id']}/profile",
            headers={"X-CSRF-Token": token},
            json={"display_color": "url(evil)", "family_visible": True},
        ).status_code == 400

        owner = auth_service.get_user("owner")
        assert owner["family_visible"] is False
        owner_update = client.put(
            f"/api/admin/users/{owner['user_id']}/profile",
            headers={"X-CSRF-Token": token},
            json={"display_color": "blue", "family_visible": True},
        )
        assert owner_update.status_code == 200
        assert list_family_people()[0]["user_id"] == owner["user_id"]

        wall = create(client, token, "wall", "wall_display").json()["user"]
        wall_update = client.put(
            f"/api/admin/users/{wall['user_id']}/profile",
            headers={"X-CSRF-Token": token},
            json={"display_color": "green", "family_visible": True},
        )
        assert wall_update.status_code == 200
        assert wall_update.json()["user"]["family_visible"] is False
        users_response = client.get("/api/admin/users")
        assert users_response.status_code == 200
        assert "password_hash" not in users_response.text
        assert valid_password() not in users_response.text


def test_owner_password_reset_invalidates_session_and_replaces_password():
    with environment() as owner_client:
        token = login(owner_client)
        user = create(owner_client, token, "voksen", "adult").json()["user"]
        with TestClient(app, follow_redirects=False) as user_client:
            assert user_client.post("/api/auth/login", json={"username": "voksen", "password": valid_password()}).status_code == 200
            assert user_client.get("/api/auth/me").status_code == 200
            new_password = "".join(["Nyt", "-Sikkert", "-Passord", "-43!"])
            response = owner_client.post(
                f"/api/admin/users/{user['user_id']}/password",
                headers={"X-CSRF-Token": token},
                json={"password": new_password},
            )
            assert response.status_code == 200
            assert "password" not in response.text.lower()
            assert "hash" not in response.text.lower()
            assert user_client.get("/api/auth/me").status_code == 401
            assert user_client.post("/api/auth/login", json={"username": "voksen", "password": valid_password()}).status_code == 401
            assert user_client.post("/api/auth/login", json={"username": "voksen", "password": new_password}).status_code == 200

        assert owner_client.post(
            f"/api/admin/users/{user['user_id']}/password",
            headers={"X-CSRF-Token": token},
            json={"password": "short"},
        ).status_code == 400
        owner = auth_service.get_user("owner")
        assert owner_client.post(
            f"/api/admin/users/{owner['user_id']}/password",
            headers={"X-CSRF-Token": token},
            json={"password": "Another-Safe-Password-44!"},
        ).status_code == 400


def test_delete_user_invalidates_session_and_cleans_dependent_references():
    with environment() as owner_client:
        token = login(owner_client)
        user = create(owner_client, token, "barn", "child").json()["user"]
        user_id = user["user_id"]
        assignment_store = FamilyTaskAssignmentStore(config.DB_PATH)
        assignment_store.set("todo.test", "task-1", user_id)
        connection = connect()
        ensure_screen_table(connection)
        connection.execute(
            "INSERT INTO screens (slug, name, screen_type, modules, module_layout, display_options, wall_user_id, is_active, created_at, updated_at) VALUES ('test', 'Test', 'wall-large', 'routine', '{}', '{}', ?, 1, 'now', 'now')",
            (user_id,),
        )
        connection.commit()
        connection.close()
        routine_store.snapshot(person_id=user_id)
        definition_payload = definition_to_dict(definition_store.get("morning"))
        definition_payload["label"] = "Barn"
        definition_store.update("morning", definition_payload, person_id=user_id)

        with TestClient(app, follow_redirects=False) as user_client:
            assert user_client.post("/api/auth/login", json={"username": "barn", "password": valid_password()}).status_code == 200
            response = owner_client.delete(
                f"/api/admin/users/{user_id}", headers={"X-CSRF-Token": token}
            )
            assert response.status_code == 200
            assert user_client.get("/api/auth/me").status_code == 401

        assert auth_service.get_user("barn") is None
        assert assignment_store.get("todo.test", "task-1") is None
        connection = connect()
        assert connection.execute("SELECT wall_user_id FROM screens WHERE slug = 'test'").fetchone()[0] is None
        connection.close()
        assert user_id not in routine_store._load_raw_unlocked()["persons"]
        assert user_id not in definition_store._read_state_unlocked()["persons"]
        assert owner_client.delete(
            f"/api/admin/users/{user_id}", headers={"X-CSRF-Token": token}
        ).status_code == 404
        owner = auth_service.get_user("owner")
        assert owner_client.delete(
            f"/api/admin/users/{owner['user_id']}", headers={"X-CSRF-Token": token}
        ).status_code == 400

        for username, role in [("voksen", "adult"), ("vaeg", "wall_display")]:
            other = create(owner_client, token, username, role).json()["user"]
            assert owner_client.delete(
                f"/api/admin/users/{other['user_id']}", headers={"X-CSRF-Token": token}
            ).status_code == 200
            assert auth_service.get_user(username) is None


def test_all_user_management_writes_are_owner_only_and_csrf_protected():
    paths = [
        ("PUT", "/api/admin/users/target/profile", {"display_color": "blue", "family_visible": True}),
        ("POST", "/api/admin/users/target/password", {"password": valid_password()}),
        ("DELETE", "/api/admin/users/target", None),
    ]
    for role in ["adult", "child", "wall_display"]:
        with environment() as client:
            token = login(client, role)
            for method, path, payload in paths:
                response = client.request(method, path, headers={"X-CSRF-Token": token}, json=payload)
                assert response.status_code == 403
    with environment() as client:
        token = login(client)
        user = create(client, token, "target", "adult").json()["user"]
        assert client.put(
            f"/api/admin/users/{user['user_id']}/profile",
            json={"display_color": "blue", "family_visible": True},
        ).status_code == 403


if __name__ == "__main__":
    test_owner_can_create_supported_users_and_only_wall_users_are_assignable()
    test_non_owner_cannot_create_users()
    test_duplicate_invalid_role_owner_role_and_invalid_password_are_rejected()
    test_disabled_wall_user_is_not_assignable()
    test_owner_manages_profile_with_bounded_colors_and_family_visibility()
    test_owner_password_reset_invalidates_session_and_replaces_password()
    test_delete_user_invalidates_session_and_cleans_dependent_references()
    test_all_user_management_writes_are_owner_only_and_csrf_protected()
