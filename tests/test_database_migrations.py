import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from app import migrations
from app.migrations import (
    MIGRATION_SCHEMA,
    applied_migrations,
    run_migrations,
)


def test_empty_database_gets_baseline_migration():
    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder) / "jarvis.db")

        assert run_migrations(db_path) == [1, 2, 3]

        rows = applied_migrations(db_path)
        assert [(row["version"], row["name"]) for row in rows] == [
            (1, "v0.20 migration framework baseline"),
            (2, "v0.20 bootstrap and managed setup tables"),
            (3, "v0.23 user profile colors and family visibility"),
        ]

        connection = sqlite3.connect(db_path)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        connection.close()
        assert {
            "app_settings",
            "app_secrets",
            "auth_users",
            "auth_sessions",
            "auth_login_attempts",
            "managed_home_assistant_requests",
        }.issubset(tables)


def test_migrations_are_idempotent():
    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder) / "jarvis.db")

        assert run_migrations(db_path) == [1, 2, 3]
        assert run_migrations(db_path) == []
        assert len(applied_migrations(db_path)) == 3


def test_existing_database_data_is_preserved():
    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder) / "jarvis.db")

        connection = sqlite3.connect(db_path)
        connection.execute(
            "CREATE TABLE existing_data (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO existing_data (value) VALUES (?)",
            ("behold mig",),
        )
        connection.commit()
        connection.close()

        assert run_migrations(db_path) == [1, 2, 3]

        connection = sqlite3.connect(db_path)
        row = connection.execute(
            "SELECT value FROM existing_data WHERE id = 1"
        ).fetchone()
        connection.close()

        assert row == ("behold mig",)


def test_schema_creation_is_safe_before_first_migration():
    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder) / "jarvis.db")

        connection = sqlite3.connect(db_path)
        connection.execute(MIGRATION_SCHEMA)
        connection.commit()
        connection.close()

        assert run_migrations(db_path) == [1, 2, 3]


def test_v022_users_receive_safe_profile_defaults():
    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder) / "jarvis.db")
        connection = sqlite3.connect(db_path)
        connection.executescript(
            """
            CREATE TABLE auth_users (
                user_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL, role TEXT NOT NULL,
                password_hash TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_login_at TEXT
            );
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL
            );
            INSERT INTO schema_migrations VALUES (1, 'old', 'now');
            INSERT INTO schema_migrations VALUES (2, 'old', 'now');
            """
        )
        for user_id, role in [("owner-id", "owner"), ("adult-id", "adult"), ("child-id", "child"), ("wall-id", "wall_display")]:
            connection.execute(
                "INSERT INTO auth_users VALUES (?, ?, ?, ?, 'hash', 0, 'now', 'now', NULL)",
                (user_id, role, role, role),
            )
        connection.commit()
        connection.close()

        assert run_migrations(db_path) == [3]
        connection = sqlite3.connect(db_path)
        rows = connection.execute(
            "SELECT role, display_color, family_visible FROM auth_users ORDER BY role"
        ).fetchall()
        connection.close()
        assert rows == [
            ("adult", "teal", 1),
            ("child", "violet", 1),
            ("owner", "blue", 0),
            ("wall_display", "blue", 0),
        ]
        assert run_migrations(db_path) == []


def test_failed_migration_rolls_back_schema_and_version_record():
    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder) / "jarvis.db")

        def failing_migration(connection):
            connection.execute("CREATE TABLE must_rollback (value TEXT)")
            connection.execute("INSERT INTO must_rollback VALUES ('private')")
            raise RuntimeError("simulated migration failure")

        with patch.object(
            migrations,
            "MIGRATIONS",
            ((1, "failing migration", failing_migration),),
        ):
            try:
                run_migrations(db_path)
            except RuntimeError as exc:
                assert str(exc) == "simulated migration failure"
            else:
                raise AssertionError("A failed migration must propagate")

        connection = sqlite3.connect(db_path)
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'must_rollback'"
        ).fetchone() is None
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 0
        connection.close()


def test():
    test_empty_database_gets_baseline_migration()
    test_migrations_are_idempotent()
    test_existing_database_data_is_preserved()
    test_schema_creation_is_safe_before_first_migration()
    test_v022_users_receive_safe_profile_defaults()
    test_failed_migration_rolls_back_schema_and_version_record()
    print("Database migration tests OK")


if __name__ == "__main__":
    test()
