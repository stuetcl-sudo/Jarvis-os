import base64
import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken


SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

SECRETS_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_secrets (
    key TEXT PRIMARY KEY,
    encrypted_value TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _db_path(db_path=None):
    return db_path or os.getenv("DB_PATH", "/data/jarvis.db")


def _connect(db_path=None):
    path = _db_path(db_path)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _master_key_path(db_path=None):
    configured = os.getenv("CONFIG_MASTER_KEY_FILE", "").strip()
    if configured:
        return configured
    return os.path.join(os.path.dirname(os.path.abspath(_db_path(db_path))), "config-master.key")


def _persistent_master_key(db_path=None):
    path = _master_key_path(db_path)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = handle.read().strip()
    except FileNotFoundError:
        value = ""
    if value:
        return value

    os.makedirs(os.path.dirname(path), exist_ok=True)
    generated = secrets.token_urlsafe(48)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        with open(path, "r", encoding="utf-8") as handle:
            value = handle.read().strip()
        if not value:
            raise RuntimeError("CONFIG_MASTER_KEY file is empty")
        return value
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(generated)
        handle.flush()
        os.fsync(handle.fileno())
    return generated


def init_settings_store(db_path=None):
    conn = _connect(db_path)
    conn.execute(SETTINGS_SCHEMA)
    conn.execute(SECRETS_SCHEMA)
    conn.commit()
    conn.close()


def _fernet(master_key=None, db_path=None):
    source = master_key or os.getenv("CONFIG_MASTER_KEY", "") or _persistent_master_key(db_path)
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def get_setting(key, default=None, db_path=None):
    init_settings_store(db_path)
    conn = _connect(db_path)
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value, db_path=None):
    if not isinstance(key, str) or not key.strip():
        raise ValueError("Setting key is required")
    if value is None:
        delete_setting(key, db_path=db_path)
        return None
    init_settings_store(db_path)
    conn = _connect(db_path)
    conn.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key.strip(), str(value), _now_iso()),
    )
    conn.commit()
    conn.close()
    return str(value)


def delete_setting(key, db_path=None):
    init_settings_store(db_path)
    conn = _connect(db_path)
    conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
    conn.commit()
    conn.close()


def has_secret(key, db_path=None):
    init_settings_store(db_path)
    conn = _connect(db_path)
    row = conn.execute("SELECT 1 FROM app_secrets WHERE key = ?", (key,)).fetchone()
    conn.close()
    return bool(row)


def set_secret(key, value, db_path=None, master_key=None):
    if not isinstance(key, str) or not key.strip():
        raise ValueError("Secret key is required")
    if value is None or value == "":
        delete_secret(key, db_path=db_path)
        return None
    encrypted = _fernet(master_key, db_path).encrypt(str(value).encode("utf-8")).decode("ascii")
    init_settings_store(db_path)
    conn = _connect(db_path)
    conn.execute(
        """
        INSERT INTO app_secrets (key, encrypted_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET encrypted_value = excluded.encrypted_value, updated_at = excluded.updated_at
        """,
        (key.strip(), encrypted, _now_iso()),
    )
    conn.commit()
    conn.close()
    return True


def get_secret(key, default=None, db_path=None, master_key=None):
    init_settings_store(db_path)
    conn = _connect(db_path)
    row = conn.execute("SELECT encrypted_value FROM app_secrets WHERE key = ?", (key,)).fetchone()
    conn.close()
    if not row:
        return default
    try:
        return _fernet(master_key, db_path).decrypt(row["encrypted_value"].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Stored secret could not be decrypted with CONFIG_MASTER_KEY") from exc


def delete_secret(key, db_path=None):
    init_settings_store(db_path)
    conn = _connect(db_path)
    conn.execute("DELETE FROM app_secrets WHERE key = ?", (key,))
    conn.commit()
    conn.close()


def public_connection_summary(db_path=None):
    return {
        "home_assistant_url": get_setting("home_assistant.base_url", "", db_path=db_path),
        "home_assistant_token_configured": has_secret("home_assistant.token", db_path=db_path),
    }


def set_home_assistant_connection(base_url, token, db_path=None, master_key=None):
    """Persist the HA URL and encrypted token in one database transaction."""
    encrypted = _fernet(master_key, db_path).encrypt(str(token).encode("utf-8")).decode("ascii")
    now = _now_iso()
    init_settings_store(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            ("home_assistant.base_url", str(base_url), now),
        )
        conn.execute(
            """
            INSERT INTO app_secrets (key, encrypted_value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET encrypted_value = excluded.encrypted_value, updated_at = excluded.updated_at
            """,
            ("home_assistant.token", encrypted, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return True
