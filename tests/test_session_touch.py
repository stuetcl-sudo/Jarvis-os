import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import config
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db


def password():
    return "".join(["Session", "Touch", "Pass", "-42!"])


def last_seen_at(db_path):
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT last_seen_at FROM auth_sessions LIMIT 1").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_session_last_seen_is_throttled():
    previous_db = config.DB_PATH
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "session_touch.db")
        try:
            init_db()
            initialize_auth_tables()
            auth_service.create_user("session-owner", "Session Owner", "owner", password())
            now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
            session = auth_service.authenticate("session-owner", password(), "192.0.2.10", now=now)
            original = last_seen_at(config.DB_PATH)

            assert auth_service.resolve_session(session["session_value"], now=now + timedelta(minutes=1))
            assert last_seen_at(config.DB_PATH) == original

            assert auth_service.resolve_session(session["session_value"], now=now + timedelta(minutes=6))
            assert last_seen_at(config.DB_PATH) != original
        finally:
            config.DB_PATH = previous_db


def test():
    test_session_last_seen_is_throttled()
    print("Session touch tests OK")


if __name__ == "__main__":
    test()
