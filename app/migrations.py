"""Small, transactional SQLite migration runner for Jarvis-os."""

import os
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone

from app import config


Migration = tuple[int, str, Callable[[sqlite3.Connection], None]]

MIGRATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _migration_1_baseline(connection: sqlite3.Connection) -> None:
    """Record the v0.20 migration framework without changing existing data."""
    connection.execute("SELECT 1")


def _migration_2_bootstrap_and_managed_setup(connection: sqlite3.Connection) -> None:
    """Create the v0.20 bootstrap, settings, and managed-installer persistence."""
    from app.auth.service import (
        AUTH_LOGIN_ATTEMPTS_SCHEMA,
        AUTH_SESSIONS_SCHEMA,
        AUTH_USERS_SCHEMA,
    )
    from app.managed_home_assistant_installer import REQUEST_SCHEMA
    from app.settings_store import SECRETS_SCHEMA, SETTINGS_SCHEMA

    for schema in (
        SETTINGS_SCHEMA,
        SECRETS_SCHEMA,
        AUTH_USERS_SCHEMA,
        AUTH_SESSIONS_SCHEMA,
        AUTH_LOGIN_ATTEMPTS_SCHEMA,
        REQUEST_SCHEMA,
    ):
        connection.execute(schema)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at)"
    )


def _migration_3_user_profiles(connection: sqlite3.Connection) -> None:
    """Add bounded family profile fields without exposing owners or wall accounts."""
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(auth_users)").fetchall()}
    if "display_color" not in columns:
        connection.execute("ALTER TABLE auth_users ADD COLUMN display_color TEXT NOT NULL DEFAULT 'blue'")
    if "family_visible" not in columns:
        connection.execute("ALTER TABLE auth_users ADD COLUMN family_visible INTEGER NOT NULL DEFAULT 0")
        connection.execute("UPDATE auth_users SET family_visible = 1 WHERE role IN ('adult', 'child')")
    connection.execute(
        "UPDATE auth_users SET display_color = CASE role WHEN 'adult' THEN 'teal' WHEN 'child' THEN 'violet' ELSE 'blue' END WHERE display_color IS NULL OR display_color = 'blue'"
    )
    connection.execute("UPDATE auth_users SET family_visible = 0 WHERE role = 'wall_display'")


MIGRATIONS: tuple[Migration, ...] = (
    (1, "v0.20 migration framework baseline", _migration_1_baseline),
    (2, "v0.20 bootstrap and managed setup tables", _migration_2_bootstrap_and_managed_setup),
    (3, "v0.23 user profile colors and family visibility", _migration_3_user_profiles),
)


def applied_migrations(db_path: str | None = None) -> list[dict]:
    connection = _connect(db_path)
    try:
        connection.execute(MIGRATION_SCHEMA)
        rows = connection.execute(
            """
            SELECT version, name, applied_at
            FROM schema_migrations
            ORDER BY version ASC
            """
        ).fetchall()
        connection.commit()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def run_migrations(db_path: str | None = None) -> list[int]:
    """Apply pending migrations once, in version order and transactionally."""
    connection = _connect(db_path)
    applied_now: list[int] = []

    try:
        connection.execute(MIGRATION_SCHEMA)

        existing = {
            int(row["version"])
            for row in connection.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }

        versions = [version for version, _, _ in MIGRATIONS]
        if versions != sorted(versions) or len(versions) != len(set(versions)):
            raise RuntimeError("Migration versions must be unique and ordered")

        for version, name, migration in MIGRATIONS:
            if version in existing:
                continue

            try:
                connection.execute("BEGIN")
                migration(connection)
                connection.execute(
                    """
                    INSERT INTO schema_migrations (version, name, applied_at)
                    VALUES (?, ?, ?)
                    """,
                    (version, name, _now_iso()),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

            applied_now.append(version)

        return applied_now
    finally:
        connection.close()
