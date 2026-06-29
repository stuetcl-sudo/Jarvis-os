import os
import sqlite3
from datetime import datetime, timezone

from app import config


ACTION_SCHEMA = """
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

INCIDENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    severity TEXT NOT NULL,
    service TEXT,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT,
    resolved_at TEXT
)
"""

CHECK_SCHEMA = """
CREATE TABLE IF NOT EXISTS worker_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    docker_total INTEGER NOT NULL,
    docker_running INTEGER NOT NULL,
    docker_stopped INTEGER NOT NULL,
    cpu_percent REAL NOT NULL,
    memory_percent REAL NOT NULL,
    swap_percent REAL NOT NULL,
    disk_percent REAL NOT NULL,
    detail TEXT
)
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def connect():
    folder = os.path.dirname(config.DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = connect()
    conn.execute(ACTION_SCHEMA)
    conn.execute(INCIDENT_SCHEMA)
    conn.execute(CHECK_SCHEMA)
    conn.commit()
    conn.close()


def log_action(action, target, status, reason=None):
    conn = connect()
    conn.execute(
        "INSERT INTO action_log (created_at, action, target, status, reason, safe_mode) VALUES (?, ?, ?, ?, ?, ?)",
        (now_iso(), action, target, status, reason, 1 if config.SAFE_MODE else 0),
    )
    conn.commit()
    conn.close()


def list_actions(limit=100):
    safe_limit = max(1, min(int(limit), 500))
    conn = connect()
    rows = conn.execute("SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (safe_limit,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def log_worker_check(status, docker_total, docker_running, docker_stopped, cpu_percent, memory_percent, swap_percent, disk_percent, detail=None):
    conn = connect()
    conn.execute(
        "INSERT INTO worker_checks (created_at, status, docker_total, docker_running, docker_stopped, cpu_percent, memory_percent, swap_percent, disk_percent, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (now_iso(), status, docker_total, docker_running, docker_stopped, cpu_percent, memory_percent, swap_percent, disk_percent, detail),
    )
    conn.commit()
    conn.close()


def latest_worker_check():
    conn = connect()
    row = conn.execute("SELECT * FROM worker_checks ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None


def create_incident(severity, service, title, detail):
    conn = connect()
    existing = conn.execute(
        "SELECT * FROM incidents WHERE service IS ? AND title = ? AND resolved_at IS NULL LIMIT 1",
        (service, title),
    ).fetchone()
    if existing:
        conn.close()
        return dict(existing)
    conn.execute(
        "INSERT INTO incidents (created_at, severity, service, status, title, detail, resolved_at) VALUES (?, ?, ?, ?, ?, ?, NULL)",
        (now_iso(), severity, service, "active", title, detail),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM incidents ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row)


def resolve_incident(service, title):
    conn = connect()
    conn.execute(
        "UPDATE incidents SET status = ?, resolved_at = ? WHERE service IS ? AND title = ? AND resolved_at IS NULL",
        ("resolved", now_iso(), service, title),
    )
    conn.commit()
    conn.close()


def list_incidents(active_only=True, limit=100):
    safe_limit = max(1, min(int(limit), 500))
    conn = connect()
    if active_only:
        rows = conn.execute("SELECT * FROM incidents WHERE resolved_at IS NULL ORDER BY id DESC LIMIT ?", (safe_limit,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM incidents ORDER BY id DESC LIMIT ?", (safe_limit,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def count_recent_failed_actions(action, target, minutes):
    conn = connect()
    rows = conn.execute(
        "SELECT COUNT(*) AS total FROM action_log WHERE action = ? AND target = ? AND status = 'error' AND created_at >= datetime('now', ?)",
        (action, target, f"-{int(minutes)} minutes"),
    ).fetchone()
    conn.close()
    return int(rows["total"] if rows else 0)
