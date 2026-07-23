import sqlite3
import tempfile
from pathlib import Path

from app.migrations import (
    MIGRATION_SCHEMA,
    applied_migrations,
    run_migrations,
)


def test_empty_database_gets_baseline_migration():
    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder) / "jarvis.db")

        assert run_migrations(db_path) == [1]

        rows = applied_migrations(db_path)
        assert len(rows) == 1
        assert rows[0]["version"] == 1
        assert rows[0]["name"] == "v0.20 migration framework baseline"


def test_migrations_are_idempotent():
    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder) / "jarvis.db")

        assert run_migrations(db_path) == [1]
        assert run_migrations(db_path) == []
        assert len(applied_migrations(db_path)) == 1


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

        assert run_migrations(db_path) == [1]

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

        assert run_migrations(db_path) == [1]


def test():
    test_empty_database_gets_baseline_migration()
    test_migrations_are_idempotent()
    test_existing_database_data_is_preserved()
    test_schema_creation_is_safe_before_first_migration()
    print("Database migration tests OK")


if __name__ == "__main__":
    test()
