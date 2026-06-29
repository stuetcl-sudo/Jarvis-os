import os
import sqlite3
from datetime import datetime, timezone

from app import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    status TEXT NOT NULL,
    reason TEXT,
    safe_mode INTEGER NOT NULL
)
"""


def connect():
    folder = os.path.dirname(config.DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = connect()
    conn.execute(SCHEMA)
    conn.commit()
    conn.close()


def log_action(action, target, status, reason=None):
    conn = connect()
    conn.execute(
        "INSERT INTO action_log (created_at, action, target, status, reason, safe_mode) VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), action, target, status, reason, 1 if config.SAFE_MODE else 0),
    )
    conn.commit()
    conn.close()


def list_actions(limit=100):
    safe_limit = max(1, min(int(limit), 500))
    conn = connect()
    rows = conn.execute("SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (safe_limit,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]
