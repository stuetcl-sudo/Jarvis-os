import contextlib
import importlib
import io
import sqlite3
import tempfile
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from pydantic.warnings import UnsupportedFieldAttributeWarning

from app import config
from app.actions.engine import action_engine
from app.auth import routes as auth_routes
from app.auth import service as auth_module
from app.auth.cli import main as cli_main
from app.auth.context import reset_current_actor, set_current_actor
from app.auth.dependencies import safe_next_path
from app.auth.service import ALLOWED_ROLES, DUMMY_CREDENTIAL_HASH, InvalidCredentials, LoginRateLimited, auth_service, hash_session_token, initialize_auth_tables, rate_limit_key
from app.db import init_db
from app.main_auth import app

ROOT = Path(__file__).resolve().parents[1]
MODULE_DB_DIR = tempfile.TemporaryDirectory()
config.DB_PATH = str(Path(MODULE_DB_DIR.name) / "module.db")


def password():
    return "".join(["Local", "Test", "Pass", "-42!"])


@contextlib.contextmanager
def environment():
    previous = (config.DB_PATH, config.AUTH_COOKIE_SECURE, config.AUTH_LOGIN_MAX_FAILURES, config.AUTH_LOGIN_WINDOW_MINUTES)
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "auth.db")
        config.AUTH_COOKIE_SECURE = False
        config.AUTH_LOGIN_MAX_FAILURES = 5
        config.AUTH_LOGIN_WINDOW_MINUTES = 15
        init_db()
        initialize_auth_tables()
        client = TestClient(app, follow_redirects=False)
        try:
            yield client
        finally:
            client.close()
            config.DB_PATH, config.AUTH_COOKIE_SECURE, config.AUTH_LOGIN_MAX_FAILURES, config.AUTH_LOGIN_WINDOW_MINUTES = previous


def rows(sql, values=()):
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, values).fetchall()
    finally:
        conn.close()


def create(role="owner"):
    return auth_service.create_user(f"test-{role}", f"Test {role}", role, password())


def login(client, role="owner"):
    response = client.post("/api/auth/login", json={"username": f"test-{role}", "password": password()})
    assert response.status_code == 200, response.text
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    return me.json()


def test_login_payload_password_alias_has_no_unsupported_field_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error", UnsupportedFieldAttributeWarning)
        routes_module = importlib.reload(auth_routes)
        payload = routes_module.LoginPayload.model_validate(
            {"username": "test-owner", "password": password()}
        )
        schema = routes_module.LoginPayload.model_json_schema(by_alias=True)

    assert payload.username == "test-owner"
    assert payload.credential_value == password()
    assert payload.model_dump(by_alias=True) == {
        "username": "test-owner",
        "password": password(),
    }
    assert set(schema["properties"]) == {"username", "password"}
    assert "password" in schema["required"]

    for invalid_payload in [
        {"username": "test-owner"},
        {"username": "test-owner", "password": None},
    ]:
        try:
            routes_module.LoginPayload.model_validate(invalid_payload)
            raise AssertionError("invalid password payload accepted")
        except ValidationError:
            pass

    with environment() as client:
        create()
        assert client.post("/api/auth/login", json={"username": "test-owner"}).status_code == 422
        assert client.post(
            "/api/auth/login",
            json={"username": "test-owner", "password": password() + "x"},
        ).status_code == 401


def test_user_storage_roles_and_cli():
    with environment():
        initialize_auth_tables()
        tables = {row["name"] for row in rows("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"auth_users", "auth_sessions", "auth_login_attempts"}.issubset(tables)
        for role in sorted(ALLOWED_ROLES):
            assert create(role)["role"] == role
        try:
            auth_service.create_user("TEST-OWNER", "Duplicate", "owner", password())
            raise AssertionError("duplicate username accepted")
        except ValueError:
            pass
        try:
            auth_service.create_user("bad-role", "Bad", "guest", password())
            raise AssertionError("invalid role accepted")
        except ValueError:
            pass
        for invalid_password in ["x" * 11, "x" * 129]:
            try:
                auth_service.create_user(f"bad-{len(invalid_password)}", "Bad password", "adult", invalid_password)
                raise AssertionError("invalid password length accepted")
            except ValueError:
                pass
        stored = rows("SELECT username, password_hash FROM auth_users")
        assert stored and all(item["password_hash"].startswith("$argon2") for item in stored)
        assert password().encode() not in Path(config.DB_PATH).read_bytes()
        assert all("password_hash" not in user for user in auth_service.list_users())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert cli_main(["list-users"]) == 0
        assert "$argon2" not in output.getvalue() and "password_hash" not in output.getvalue()


def test_login_dummy_rate_limit_and_sessions():
    with environment() as client:
        create()
        wrong = client.post("/api/auth/login", json={"username": "test-owner", "password": password() + "x"})
        missing = client.post("/api/auth/login", json={"username": "missing-user", "password": password()})
        assert wrong.status_code == missing.status_code == 401
        assert wrong.json() == missing.json()

        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        original = auth_module.CREDENTIAL_HASHER
        seen = []

        class SpyHasher:
            def hash(self, supplied):
                return original.hash(supplied)

            def verify(self, supplied, stored):
                seen.append(stored)
                return original.verify(supplied, stored)

        with patch.object(auth_module, "CREDENTIAL_HASHER", SpyHasher()):
            try:
                auth_service.authenticate("not-present", password(), "192.0.2.2", now=now)
            except InvalidCredentials:
                pass
        assert seen == [DUMMY_CREDENTIAL_HASH]

        clear_key = rate_limit_key("test-owner", "198.51.100.9")
        try:
            auth_service.authenticate("test-owner", password() + "x", "198.51.100.9", now=now)
        except InvalidCredentials:
            pass
        assert rows("SELECT 1 FROM auth_login_attempts WHERE rate_limit_key = ?", (clear_key,))
        auth_service.authenticate("test-owner", password(), "198.51.100.9", now=now + timedelta(seconds=1))
        assert not rows("SELECT 1 FROM auth_login_attempts WHERE rate_limit_key = ?", (clear_key,))

        config.AUTH_LOGIN_MAX_FAILURES = 3
        for second in range(2):
            try:
                auth_service.authenticate("test-owner", password() + "x", "198.51.100.1", now=now + timedelta(seconds=second))
            except InvalidCredentials:
                pass
        try:
            auth_service.authenticate("test-owner", password() + "x", "198.51.100.1", now=now + timedelta(seconds=3))
            raise AssertionError("rate limit did not lock")
        except LoginRateLimited:
            pass
        key = rate_limit_key("test-owner", "198.51.100.1")
        assert rows("SELECT locked_until FROM auth_login_attempts WHERE rate_limit_key = ?", (key,))[0]["locked_until"]

        first = client.post("/api/auth/login", json={"username": "test-owner", "password": password()})
        header = first.headers["set-cookie"].lower()
        assert first.status_code == 200 and "httponly" in header and "samesite=strict" in header and "secure" not in header
        raw_first = client.cookies.get("jarvis_session")
        assert rows("SELECT session_token_hash FROM auth_sessions")[0]["session_token_hash"] == hash_session_token(raw_first)
        assert raw_first not in Path(config.DB_PATH).read_text(errors="ignore")
        second = client.post("/api/auth/login", json={"username": "test-owner", "password": password()})
        assert second.status_code == 200 and client.cookies.get("jarvis_session") != raw_first
        assert len(rows("SELECT 1 FROM auth_sessions")) == 1
        me = client.get("/api/auth/me").json()
        assert client.post("/api/auth/logout").status_code == 403
        assert client.post("/api/auth/logout", headers={"X-CSRF-Token": me["csrf_token"]}).status_code == 200
        assert not rows("SELECT 1 FROM auth_sessions")

    with environment():
        create()
        now = datetime(2026, 2, 1, tzinfo=timezone.utc)
        session = auth_service.authenticate("test-owner", password(), "203.0.113.1", now=now)
        assert auth_service.resolve_session(session["session_value"], now=now + timedelta(hours=config.AUTH_SESSION_HOURS + 1)) is None

    with environment() as client:
        create()
        login(client)
        auth_service.set_user_disabled("test-owner", True)
        assert client.get("/api/auth/me").status_code == 401
        assert not rows("SELECT 1 FROM auth_sessions")
        disabled_login = client.post("/api/auth/login", json={"username": "test-owner", "password": password()})
        assert disabled_login.status_code == 401

    with environment() as client:
        config.AUTH_COOKIE_SECURE = True
        create()
        response = client.post("/api/auth/login", json={"username": "test-owner", "password": password()})
        assert "secure" in response.headers["set-cookie"].lower()

    with environment():
        create("wall_display")
        now = datetime(2026, 2, 1, tzinfo=timezone.utc)
        session = auth_service.authenticate("test-wall_display", password(), "203.0.113.2", now=now)
        expiry = datetime.fromisoformat(session["expires_at"])
        assert expiry - now == timedelta(days=config.AUTH_WALL_SESSION_DAYS)


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


def send(client, case, headers=None):
    path, payload = case
    return client.post(path, json=payload, headers=headers or {}) if payload is not None else client.post(path, headers=headers or {})


def test_roles_write_protection_and_handler_reachability():
    with environment() as client:
        assert client.get("/").status_code == 200
        redirect = client.get("/admin")
        assert redirect.status_code == 303 and redirect.headers["location"] == "/login?next=/admin"
        for case in write_cases():
            assert send(client, case).status_code == 401

    for role in ["adult", "child", "wall_display"]:
        with environment() as client:
            create(role)
            login(client, role)
            assert client.get("/admin").status_code == 403
            for case in write_cases():
                assert send(client, case).status_code == 403

    with environment() as client:
        create()
        me = login(client)
        assert client.get("/admin").status_code == 200
        for case in write_cases():
            assert send(client, case).status_code == 403
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
                assert send(client, case, headers).status_code == 200, case[0]


def test_actor_csrf_redirect_and_frontend_contract():
    actor_context = set_current_actor("session-owner")
    try:
        queued = {"action_id": "a", "asset_id": "docker:example", "action_type": "docker.start_container", "status": "queued", "deduplicated": True}
        with patch("app.actions.engine.queue_action", return_value=queued) as call:
            action_engine.queue_action(asset_id="docker:example", action_type="docker.start_container", requested_by="spoofed", source="spoofed")
            assert call.call_args.kwargs["requested_by"] == "session-owner"
            assert call.call_args.kwargs["source"] == "mission_control"

        transition = SimpleNamespace(changed=False, action={"asset_id": "docker:example"}, reason=None)
        with patch("app.actions.engine.approve_action", return_value=transition) as call:
            result = action_engine.approve_action("a", "spoofed")
            assert call.call_args.args == ("a", "session-owner")
            assert result == transition.action
        with patch("app.actions.engine.deny_action", return_value=transition) as call:
            result = action_engine.deny_action("a", "spoofed")
            assert call.call_args.args == ("a", "session-owner")
            assert result == transition.action
        with patch("app.actions.engine.cancel_action", return_value=transition) as call:
            result = action_engine.cancel_action("a", "spoofed")
            assert call.call_args.args == ("a", "session-owner")
            assert result == transition.action

        with patch("app.actions.engine.get_action", return_value=None) as call:
            assert action_engine.run_action("a") is None
            call.assert_called_once_with("a")
    finally:
        reset_current_actor(actor_context)

    for unsafe in ["//evil.example", "https://evil.example", "/\\evil", "admin", ""]:
        assert safe_next_path(unsafe) is None

    for valid in ["/", "/wall", "/admin", "/login?next=/wall"]:
        assert safe_next_path(valid) == valid

    login_js = (ROOT / "app/static/js/login.js").read_text()
    admin_js = (ROOT / "app/static/js/admin.js").read_text()
    family_js = (ROOT / "app/static/js/family.js").read_text()
    combined_js = login_js + admin_js + family_js
    assert "localStorage" not in combined_js
    assert "sessionStorage" not in combined_js
    assert "innerHTML" not in combined_js

    assert 'credentials: "same-origin"' in login_js
    assert 'options.credentials = "same-origin"' in admin_js
    for endpoint in [
        "/api/mission",
        "/api/family/weather",
        "/api/family/calendar",
        "/api/health",
    ]:
        expected = f'fetch("{endpoint}", {{ credentials: "same-origin" }})'
        assert expected in family_js
    assert family_js.count('credentials: "same-origin"') == 4

    assert "csrf_token" in admin_js + family_js
    assert "X-CSRF-Token" in admin_js + family_js
    assert "data-role" not in login_js
    assert "requested_by" not in admin_js
    assert "source:" not in admin_js


if __name__ == "__main__":
    for test in [
        test_login_payload_password_alias_has_no_unsupported_field_warning,
        test_user_storage_roles_and_cli,
        test_login_dummy_rate_limit_and_sessions,
        test_roles_write_protection_and_handler_reachability,
        test_actor_csrf_redirect_and_frontend_contract,
    ]:
        test()
    print("Auth and role tests OK")
