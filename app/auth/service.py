import hashlib
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pwdlib import PasswordHash

from app import config
from app.db import connect, log_action

ALLOWED_ROLES = {"owner", "adult", "child", "wall_display"}
SESSION_COOKIE_NAME = "jarvis_session"
CREDENTIAL_MIN_LENGTH = 12
CREDENTIAL_MAX_LENGTH = 128
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)
GENERIC_LOGIN_ERROR = "Ugyldigt brugernavn eller adgangskode."
GENERIC_RATE_LIMIT_ERROR = "For mange loginforsøg. Prøv igen senere."

CREDENTIAL_HASHER = PasswordHash.recommended()
DUMMY_CREDENTIAL_HASH = CREDENTIAL_HASHER.hash("jarvis-dummy-password-not-a-user")
_AUTH_SCHEMA_LOCK = threading.Lock()
_AUTH_TABLE_NAMES = {"auth_users", "auth_sessions", "auth_login_attempts"}

AUTH_USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'adult', 'child', 'wall_display')),
    password_hash TEXT NOT NULL,
    disabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT
)
"""

AUTH_SESSIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_sessions (
    session_token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES auth_users(user_id) ON DELETE CASCADE
)
"""

AUTH_LOGIN_ATTEMPTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_login_attempts (
    rate_limit_key TEXT PRIMARY KEY,
    failed_count INTEGER NOT NULL,
    first_failed_at TEXT NOT NULL,
    locked_until TEXT
)
"""


class AuthError(Exception):
    pass


class InvalidCredentials(AuthError):
    pass


class LoginRateLimited(AuthError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def to_iso(value):
    return value.astimezone(timezone.utc).isoformat()


def from_iso(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def normalize_username(username):
    return str(username or "").strip().casefold()


def validate_password(password):
    if not isinstance(password, str):
        raise ValueError("Password must be text")
    if len(password) < CREDENTIAL_MIN_LENGTH:
        raise ValueError(f"Password must be at least {CREDENTIAL_MIN_LENGTH} characters")
    if len(password) > CREDENTIAL_MAX_LENGTH:
        raise ValueError(f"Password must be at most {CREDENTIAL_MAX_LENGTH} characters")


def hash_session_token(raw_value):
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


def rate_limit_key(username, client_address):
    normalized = normalize_username(username)
    address = str(client_address or "unknown")
    return hashlib.sha256(f"{normalized}\0{address}".encode("utf-8")).hexdigest()


def safe_user(row):
    return {
        "user_id": row["user_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "disabled": bool(row["disabled"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login_at": row["last_login_at"],
    }


def initialize_auth_tables():
    with _AUTH_SCHEMA_LOCK:
        conn = connect()
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            existing = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?, ?)",
                    tuple(sorted(_AUTH_TABLE_NAMES)),
                ).fetchall()
            }
            if existing == _AUTH_TABLE_NAMES:
                return
            conn.execute(AUTH_USERS_SCHEMA)
            conn.execute(AUTH_SESSIONS_SCHEMA)
            conn.execute(AUTH_LOGIN_ATTEMPTS_SCHEMA)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at)")
            conn.commit()
        finally:
            conn.close()


class AuthService:
    def initialize(self):
        initialize_auth_tables()
        self.cleanup_expired_sessions()

    def owner_exists(self):
        initialize_auth_tables()
        conn = connect()
        try:
            row = conn.execute("SELECT 1 FROM auth_users WHERE role = 'owner' AND disabled = 0 LIMIT 1").fetchone()
            return bool(row)
        finally:
            conn.close()

    def create_user(self, username, display_name, role, password):
        initialize_auth_tables()
        normalized = normalize_username(username)
        if not normalized:
            raise ValueError("Username is required")
        if role not in ALLOWED_ROLES:
            raise ValueError("Invalid role")
        validate_password(password)
        now = to_iso(utc_now())
        user_id = str(uuid4())
        credential_hash = CREDENTIAL_HASHER.hash(password)
        conn = connect()
        try:
            conn.execute(
                "INSERT INTO auth_users (user_id, username, display_name, role, password_hash, disabled, created_at, updated_at, last_login_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?, NULL)",
                (user_id, normalized, str(display_name).strip() or normalized, role, credential_hash, now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("Username already exists") from exc
        finally:
            conn.close()
        log_action("auth_user_created", normalized, "ok", f"role={role}")
        return self.get_user(normalized)

    def get_user(self, username):
        initialize_auth_tables()
        conn = connect()
        try:
            row = conn.execute("SELECT * FROM auth_users WHERE username = ? COLLATE NOCASE", (normalize_username(username),)).fetchone()
            return safe_user(row) if row else None
        finally:
            conn.close()

    def list_users(self):
        initialize_auth_tables()
        conn = connect()
        try:
            rows = conn.execute("SELECT * FROM auth_users ORDER BY username ASC").fetchall()
            return [safe_user(row) for row in rows]
        finally:
            conn.close()

    def set_user_disabled(self, username, disabled):
        initialize_auth_tables()
        normalized = normalize_username(username)
        now = to_iso(utc_now())
        conn = connect()
        try:
            row = conn.execute("SELECT user_id FROM auth_users WHERE username = ? COLLATE NOCASE", (normalized,)).fetchone()
            if not row:
                raise ValueError("User not found")
            conn.execute("UPDATE auth_users SET disabled = ?, updated_at = ? WHERE user_id = ?", (1 if disabled else 0, now, row["user_id"]))
            if disabled:
                conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (row["user_id"],))
            conn.commit()
        finally:
            conn.close()
        log_action("auth_user_disabled" if disabled else "auth_user_enabled", normalized, "ok")
        return self.get_user(normalized)

    def reset_password(self, username, password):
        initialize_auth_tables()
        validate_password(password)
        normalized = normalize_username(username)
        now = to_iso(utc_now())
        credential_hash = CREDENTIAL_HASHER.hash(password)
        conn = connect()
        try:
            row = conn.execute("SELECT user_id FROM auth_users WHERE username = ? COLLATE NOCASE", (normalized,)).fetchone()
            if not row:
                raise ValueError("User not found")
            conn.execute("UPDATE auth_users SET password_hash = ?, updated_at = ? WHERE user_id = ?", (credential_hash, now, row["user_id"]))
            conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (row["user_id"],))
            conn.commit()
        finally:
            conn.close()
        log_action("auth_password_reset", normalized, "ok")
        return self.get_user(normalized)

    def cleanup_expired_sessions(self, now=None, conn=None):
        current = to_iso(now or utc_now())
        owns_connection = conn is None
        db = conn or connect()
        try:
            deleted = db.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (current,)).rowcount
            if owns_connection:
                db.commit()
            return deleted
        finally:
            if owns_connection:
                db.close()

    def _check_locked(self, conn, key, now):
        row = conn.execute("SELECT * FROM auth_login_attempts WHERE rate_limit_key = ?", (key,)).fetchone()
        if not row:
            return False
        if row["locked_until"] and from_iso(row["locked_until"]) > now:
            return True
        window_start = from_iso(row["first_failed_at"])
        if now - window_start >= timedelta(minutes=config.AUTH_LOGIN_WINDOW_MINUTES):
            conn.execute("DELETE FROM auth_login_attempts WHERE rate_limit_key = ?", (key,))
        return False

    def _record_failure(self, conn, key, now):
        row = conn.execute("SELECT * FROM auth_login_attempts WHERE rate_limit_key = ?", (key,)).fetchone()
        window = timedelta(minutes=config.AUTH_LOGIN_WINDOW_MINUTES)
        if not row or now - from_iso(row["first_failed_at"]) >= window:
            failed_count = 1
            first_failed_at = now
        else:
            failed_count = int(row["failed_count"]) + 1
            first_failed_at = from_iso(row["first_failed_at"])
        locked_until = now + window if failed_count >= config.AUTH_LOGIN_MAX_FAILURES else None
        conn.execute(
            "INSERT INTO auth_login_attempts (rate_limit_key, failed_count, first_failed_at, locked_until) VALUES (?, ?, ?, ?) ON CONFLICT(rate_limit_key) DO UPDATE SET failed_count = excluded.failed_count, first_failed_at = excluded.first_failed_at, locked_until = excluded.locked_until",
            (key, failed_count, to_iso(first_failed_at), to_iso(locked_until) if locked_until else None),
        )
        return locked_until is not None

    def authenticate(self, username, password, client_address, now=None):
        initialize_auth_tables()
        current = now or utc_now()
        normalized = normalize_username(username)
        key = rate_limit_key(normalized, client_address)
        supplied_value = password if isinstance(password, str) and len(password) <= CREDENTIAL_MAX_LENGTH else ""
        conn = connect()
        try:
            self.cleanup_expired_sessions(current, conn)
            if self._check_locked(conn, key, current):
                conn.commit()
                raise LoginRateLimited(GENERIC_RATE_LIMIT_ERROR)
            row = conn.execute("SELECT * FROM auth_users WHERE username = ? COLLATE NOCASE", (normalized,)).fetchone()
            candidate_hash = row["password_hash"] if row else DUMMY_CREDENTIAL_HASH
            verified = CREDENTIAL_HASHER.verify(supplied_value, candidate_hash)
            if not row or not verified or bool(row["disabled"]):
                locked = self._record_failure(conn, key, current)
                conn.commit()
                if locked:
                    raise LoginRateLimited(GENERIC_RATE_LIMIT_ERROR)
                raise InvalidCredentials(GENERIC_LOGIN_ERROR)
            conn.execute("DELETE FROM auth_login_attempts WHERE rate_limit_key = ?", (key,))
            conn.execute("UPDATE auth_users SET last_login_at = ?, updated_at = ? WHERE user_id = ?", (to_iso(current), to_iso(current), row["user_id"]))
            conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (row["user_id"],))
            session_value = secrets.token_urlsafe(48)
            csrf_value = secrets.token_urlsafe(32)
            duration = timedelta(days=config.AUTH_WALL_SESSION_DAYS) if row["role"] == "wall_display" else timedelta(hours=config.AUTH_SESSION_HOURS)
            expires_at = current + duration
            conn.execute(
                "INSERT INTO auth_sessions (session_token_hash, user_id, csrf_token, created_at, expires_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?)",
                (hash_session_token(session_value), row["user_id"], csrf_value, to_iso(current), to_iso(expires_at), to_iso(current)),
            )
            conn.commit()
            result = safe_user(row)
            result["last_login_at"] = to_iso(current)
            log_action("auth_login", normalized, "ok", f"role={row['role']}")
            return {
                "user": result,
                "session_value": session_value,
                "csrf_value": csrf_value,
                "expires_at": to_iso(expires_at),
                "cookie_max_age": int(duration.total_seconds()),
            }
        finally:
            conn.close()

    def resolve_session(self, raw_value, now=None):
        if not raw_value:
            return None
        initialize_auth_tables()
        current = now or utc_now()
        session_digest = hash_session_token(raw_value)
        conn = connect()
        try:
            row = conn.execute(
                "SELECT s.*, u.username, u.display_name, u.role, u.disabled, u.created_at AS user_created_at, u.updated_at AS user_updated_at, u.last_login_at FROM auth_sessions s JOIN auth_users u ON u.user_id = s.user_id WHERE s.session_token_hash = ?",
                (session_digest,),
            ).fetchone()
            if not row:
                return None
            if bool(row["disabled"]) or from_iso(row["expires_at"]) <= current:
                conn.execute("DELETE FROM auth_sessions WHERE session_token_hash = ?", (session_digest,))
                conn.commit()
                return None
            if current - from_iso(row["last_seen_at"]) >= SESSION_TOUCH_INTERVAL:
                conn.execute("UPDATE auth_sessions SET last_seen_at = ? WHERE session_token_hash = ?", (to_iso(current), session_digest))
                conn.commit()
            return {
                "user_id": row["user_id"],
                "username": row["username"],
                "display_name": row["display_name"],
                "role": row["role"],
                "csrf_value": row["csrf_token"],
                "session_digest": session_digest,
                "expires_at": row["expires_at"],
            }
        finally:
            conn.close()

    def logout(self, raw_value, username=None):
        if not raw_value:
            return False
        initialize_auth_tables()
        conn = connect()
        try:
            deleted = conn.execute("DELETE FROM auth_sessions WHERE session_token_hash = ?", (hash_session_token(raw_value),)).rowcount
            conn.commit()
        finally:
            conn.close()
        if deleted and username:
            log_action("auth_logout", normalize_username(username), "ok")
        return bool(deleted)


auth_service = AuthService()
