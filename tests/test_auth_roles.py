import contextlib
import io
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import config
from app.actions.engine import action_engine
from app.auth import service as auth_module
from app.auth.cli import main as cli_main
from app.auth.context import reset_current_actor, set_current_actor
from app.auth.dependencies import safe_next_path
from app.auth.service import (
    ALLOWED_ROLES,
    DUMMY_PASSWORD_HASH,
    InvalidCredentials,
    LoginRateLimited,
    auth_service,
    hash_session_token,
    initialize_auth_tables,
    rate_limit_key,
)
from app.main_auth import app

ROOT = Path(__file__).resolve().parents[1]


def test_password():
    return "".join(["Local", "Test", "Pass", "-42!"])


@contextlib.contextmanager
def auth_environment():
    old_db_path = config.DB_PATH
    old_secure = config.AUTH_COOKIE_SECURE
    old_limit = config.AUTH_LOGIN_MAX_FAILURES
    old_window = config.AUTH_LOGIN_WINDOW_MINUTES
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "auth.db")
        config.AUTH_COOKIE_SECURE = False
        config.AUTH_LOGIN_MAX_FAILURES = 5
        config.AUTH_LOGIN_WINDOW_MINUTES = 15
        initialize_auth_tables()
        client = TestClient(app, follow_redirects=False)
        try:
            yield client
        finally:
            client.close()
            config.DB_PATH = old_db_path
            config.AUTH_COOKIE_SECURE = old_secure
            config.AUTH_LOGIN_MAX_FAILURES = old_limit
            config.AUTH_LOGIN_WINDOW_MINUTES = old_window


def create_user(role="owner", username=None):
    name = username or f"test-{role}"
    return auth_service.create_user(name, f"Test {role}", role, test_password())


def login(client, username="test-owner"):
    response = client.post("/api/auth/login", json={"username": username, "password": test_password()})
    assert response.status_code == 200, response.text
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    return me.json()


def database_rows(query, values=()):
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(query, values).fetchall()
    finally:
        conn.close()


def test_user_storage_and_cli_output():
    with auth_environment():
        owner = create_user()
        assert owner["role"] == "owner"
        try:
            auth_service.create_user("TEST-OWNER", "Duplicate", "owner", test_password())
            raise AssertionError("case-insensitive duplicate was accepted")
        except ValueError:
            pass
        for role in sorted(ALLOWED_ROLES - {"owner"}):
            assert create_user(role)["role"] == role
        try:
            auth_service.create_user("invalid-role", "Invalid", "guest", test_password())
            raise AssertionError("invalid role was accepted")
        except ValueError:
            pass

        rows = database_rows("SELECT username, password_hash FROM auth_users ORDER BY username")
        assert rows
        assert all(row["password_hash"].startswith("$argon2") for row in rows)
        raw_database = Path(config.DB_PATH).read_bytes()
        assert test_password().encode() not in raw_database
        users = auth_service.list_users()
        assert all("password_hash" not in user for user in users)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert cli_main(["list-users"]) == 0
        listed = output.getvalue()
        assert "$argon2" not in listed
        assert "password_hash" not in listed


def test_login_generic_errors_dummy_hash_and_disabled_user():
    with auth_environment():
        create_user()
        current = datetime(2026, 1, 1, tzinfo=timezone.utc)
        messages = []
        for username, password in [("test-owner", test_password() + "x"), ("missing-user", test_password())]:
            try:
                auth_service.authenticate(username, password, "192.0.2.1", now=current)
            except InvalidCredentials as exc:
                messages.append(str(exc))
        assert len(messages) == 2 and messages[0] == messages[1]

        original_hasher = auth_module.PASSWORD_HASHER
        calls = []

        class SpyHasher:
            def hash(self, password):
                return original_hasher.hash(password)

            def verify(self, password, password_hash):
                calls.append(password_hash)
                return original_hasher.verify(password, password_hash)

        with patch.object(auth_module, "PASSWORD_HASHER", SpyHasher()):
            try:
                auth_service.authenticate("another-missing", test_password(), "192.0.2.2", now=current)
            except InvalidCredentials:
                pass
        assert calls == [DUMMY_PASSWORD_HASH]

        auth_service.set_user_disabled("test-owner", True)
        try:
            auth_service.authenticate("test-owner", test_password(), "192.0.2.3", now=current)
            raise AssertionError("disabled user logged in")
        except InvalidCredentials:
            pass


def test_persistent_rate_limit_and_success_clear():
    with auth_environment():
        create_user()
        config.AUTH_LOGIN_MAX_FAILURES = 3
        current = datetime(2026, 2, 1, tzinfo=timezone.utc)
        for index in range(2):
            try:
                auth_service.authenticate("test-owner", test_password() + "x", "198.51.100.10", now=current + timedelta(seconds=index))
            except InvalidCredentials:
                pass
        try:
            auth_service.authenticate("test-owner", test_password() + "x", "198.51.100.10", now=current + timedelta(seconds=3))
            raise AssertionError("rate limit did not lock")
        except LoginRateLimited:
            pass
        key = rate_limit_key("test-owner", "198.51.100.10")
        assert database_rows("SELECT locked_until FROM auth_login_attempts WHERE rate_limit_key = ?", (key,))[0]["locked_until"]

    with auth_environment():
        create_user()
        current = datetime(2026, 2, 1, tzinfo=timezone.utc)
        try:
            auth_service.authenticate("test-owner", test_password() + "x", "198.51.100.11", now=current)
        except InvalidCredentials:
            pass
        auth_service.authenticate("test-owner", test_password(), "198.51.100.11", now=current + timedelta(seconds=1))
        key = rate_limit_key("test-owner", "198.51.100.11")
        assert not database_rows("SELECT 1 FROM auth_login_attempts WHERE rate_limit_key = ?", (key,))


def test_session_cookie_storage_rotation_expiry_disable_and_logout():
    with auth_environment() as client:
        create_user()
        first = client.post("/api/auth/login", json={"username": "test-owner", "password": test_password()})
        assert first.status_code == 200
        cookie_header = first.headers["set-cookie"].lower()
        assert "jarvis_session=" in cookie_header
        assert "httponly" in cookie_header
        assert "samesite=strict" in cookie_header
        assert "secure" not in cookie_header
        raw_first = client.cookies.get("jarvis_session")
        stored = database_rows("SELECT session_token_hash FROM auth_sessions")
        assert len(stored) == 1
        assert stored[0]["session_token_hash"] == hash_session_token(raw_first)
        assert raw_first not in Path(config.DB_PATH).read_text(errors="ignore")

        second = client.post("/api/auth/login", json={"username": "test-owner", "password": test_password()})
        raw_second = client.cookies.get("jarvis_session")
        assert second.status_code == 200 and raw_second != raw_first
        assert len(database_rows("SELECT session_token_hash FROM auth_sessions")) == 1

        me = client.get("/api/auth/me").json()
        assert client.post("/api/auth/logout").status_code == 403
        assert client.post("/api/auth/logout", headers={"X-CSRF-Token": me["csrf_token"]}).status_code == 200
        assert not database_rows("SELECT 1 FROM auth_sessions")
        assert client.get("/api/auth/me").status_code == 401

    with auth_environment():
        create_user()
        current = datetime(2026, 3, 1, tzinfo=timezone.utc)
        session = auth_service.authenticate("test-owner", test_password(), "203.0.113.4", now=current)
        assert auth_service.resolve_session(session["raw_token"], now=current + timedelta(hours=config.AUTH_SESSION_HOURS + 1)) is None

    with auth_environment() as client:
        create_user()
        login(client)
        auth_service.set_user_disabled("test-owner", True)
        assert client.get("/api/auth/me").status_code == 401
        assert not database_rows("SELECT 1 FROM auth_sessions")

    with auth_environment() as client:
        config.AUTH_COOKIE_SECURE = True
        create_user()
        response = client.post("/api/auth/login", json={"username": "test-owner", "password": test_password()})
        assert "secure" in response.headers["set-cookie"].lower()


def test_roles_admin_redirect_and_public_family_dashboard():
    with auth_environment() as client:
        assert client.get("/").status_code == 200
        anonymous = client.get("/admin")
        assert anonymous.status_code == 303
        assert anonymous.headers["location"] == "/login?next=/admin"

    for role in ["owner", "adult", "child", "wall_display"]:
        with auth_environment() as client:
            create_user(role)
            login(client, f"test-{role}")
            response = client.get("/admin")
            assert response.status_code == (200 if role == "owner" else 403)


def write_cases():
    return [
        ("/api/containers/example/restart", None),
        ("/api/actions/queue", {"asset_id": "docker:example", "action_type": "docker.start_container", "requested_by": "spoofed", "source": "spoofed"}),
        ("/api/actions/example/approve", None),
        ("/api/actions/example/deny", None),
        ("/api/actions/example/cancel", None),
        ("/api/actions/example/run", None),
        ("/api/worker/run-once", None),
        ("/api/recommendations/1/dismiss", None),
        ("/api/service-classifications/example", {"classification": "optional", "protected": False, "auto_start_allowed": False}),
        ("/api/policies/example/enable", None),
        ("/api/policies/example/disable", None),
    ]


def post_case(client, case, headers=None):
    path, payload = case
    return client.post(path, json=payload, headers=headers or {}) if payload is not None else client.post(path, headers=headers or {})


def test_every_write_route_requires_owner_and_csrf():
    with auth_environment() as client:
        for case in write_cases():
            assert post_case(client, case).status_code == 401, case[0]

    for role in ["adult", "child", "wall_display"]:
        with auth_environment() as client:
            create_user(role)
            login(client, f"test-{role}")
            assert post_case(client, write_cases()[0]).status_code == 403

    with auth_environment() as client:
        create_user("adult")
        login(client, "test-adult")
        for case in write_cases():
            assert post_case(client, case).status_code == 403, case[0]

    with auth_environment() as client:
        create_user()
        login(client)
        for case in write_cases():
            assert post_case(client, case).status_code == 403, case[0]


def test_owner_csrf_reaches_existing_handlers_without_docker():
    with auth_environment() as client:
        create_user()
        me = login(client)
        headers = {"X-CSRF-Token": me["csrf_token"]}
        action = {"action_id": "example", "asset_id": "docker:example", "action_type": "docker.start_container", "status": "queued", "approved": True}
        with (
            patch("app.main.list_containers", return_value=([{"name": "example", "asset_id": "docker:example"}], None)),
            patch.object(action_engine, "queue_action", return_value=action),
            patch.object(action_engine, "approve_action", return_value=action),
            patch.object(action_engine, "deny_action", return_value=action),
            patch.object(action_engine, "cancel_action", return_value=action),
            patch.object(action_engine, "run_action", return_value=action),
            patch("app.main.worker_status", return_value={"running": False}),
            patch("app.main.run_check_once", return_value={"status": "ok"}),
            patch("app.main.dismiss_recommendation", return_value=True),
            patch("app.main.upsert_service_classification", return_value={"classification": "optional", "protected": False, "auto_start_allowed": False}),
            patch.object(__import__("app.main", fromlist=["policy_engine"]).policy_engine, "set_enabled", return_value={"policy_id": "example"}),
        ):
            for case in write_cases():
                assert post_case(client, case, headers).status_code == 200, case[0]


def test_action_actor_is_derived_from_authenticated_context():
    actor_token = set_current_actor("session-owner")
    try:
        queued = {"action_id": "a", "asset_id": "docker:example", "action_type": "docker.start_container", "status": "queued", "deduplicated": True}
        with patch("app.actions.engine.queue_action", return_value=queued) as queue_call:
            action_engine.queue_action(asset_id="docker:example", action_type="docker.start_container", requested_by="spoofed", source="spoofed")
            kwargs = queue_call.call_args.kwargs
            assert kwargs["requested_by"] == "session-owner"
            assert kwargs["source"] == "mission_control"

        transition = SimpleNamespace(changed=False, action={"asset_id": "docker:example"}, reason=None)
        with patch("app.actions.engine.approve_action", return_value=transition) as approve_call:
            action_engine.approve_action("a", "spoofed")
            assert approve_call.call_args.args[1] == "session-owner"
    finally:
        reset_current_actor(actor_token)


def test_csrf_comparison_redirect_safety_and_frontend_contract():
    assert safe_next_path("/admin") == "/admin"
    assert safe_next_path("https://example.invalid/admin") is None
    assert safe_next_path("//example.invalid/admin") is None

    with auth_environment() as client:
        create_user()
        me = login(client)
        with patch("app.main_auth.hmac.compare_digest", wraps=__import__("hmac").compare_digest) as compared:
            response = client.post("/api/worker/run-once", headers={"X-CSRF-Token": me["csrf_token"] + "x"})
            assert response.status_code == 403
            assert compared.called

    assert TestClient(app).get("/login").status_code == 200
    for asset in ["/static/css/login.css", "/static/js/login.js", "/static/js/admin.js"]:
        assert TestClient(app).get(asset).status_code == 200
    admin_js = (ROOT / "app/static/js/admin.js").read_text()
    family_js = (ROOT / "app/static/js/family.js").read_text()
    login_js = (ROOT / "app/static/js/login.js").read_text()
    assert "X-CSRF-Token" in admin_js
    assert "/api/auth/me" in admin_js
    assert "localStorage" not in admin_js + login_js
    assert "csrf_token=" not in admin_js.lower()
    assert not any(method in family_js.upper() for method in ["POST", "PUT", "PATCH", "DELETE"])


if __name__ == "__main__":
    tests = [
        test_user_storage_and_cli_output,
        test_login_generic_errors_dummy_hash_and_disabled_user,
        test_persistent_rate_limit_and_success_clear,
        test_session_cookie_storage_rotation_expiry_disable_and_logout,
        test_roles_admin_redirect_and_public_family_dashboard,
        test_every_write_route_requires_owner_and_csrf,
        test_owner_csrf_reaches_existing_handlers_without_docker,
        test_action_actor_is_derived_from_authenticated_context,
        test_csrf_comparison_redirect_safety_and_frontend_contract,
    ]
    for test in tests:
        test()
    print("Authentication and role tests OK")
