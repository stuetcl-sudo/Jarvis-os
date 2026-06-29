import os
import sqlite3
from datetime import datetime, timedelta, timezone

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

SERVICE_BASELINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS service_baselines (
    service TEXT PRIMARY KEY,
    classification TEXT NOT NULL,
    normal_status TEXT NOT NULL,
    running_count INTEGER NOT NULL DEFAULT 0,
    stopped_count INTEGER NOT NULL DEFAULT 0,
    unknown_seen_count INTEGER NOT NULL DEFAULT 0,
    sample_count INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
)
"""

SYSTEM_BASELINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS system_baselines (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    sample_count INTEGER NOT NULL DEFAULT 0,
    avg_cpu_percent REAL NOT NULL DEFAULT 0,
    avg_memory_percent REAL NOT NULL DEFAULT 0,
    avg_swap_percent REAL NOT NULL DEFAULT 0,
    min_swap_percent REAL NOT NULL DEFAULT 0,
    max_swap_percent REAL NOT NULL DEFAULT 0,
    avg_disk_percent REAL NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
)
"""

OBSERVATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    service TEXT,
    title TEXT NOT NULL,
    detail TEXT NOT NULL
)
"""

RECOMMENDATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    service TEXT,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    dismissed_at TEXT
)
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def cutoff_iso(days):
    return (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()


def connect():
    folder = os.path.dirname(config.DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn, table, column, definition):
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    conn = connect()
    conn.execute(ACTION_SCHEMA)
    conn.execute(INCIDENT_SCHEMA)
    conn.execute(CHECK_SCHEMA)
    conn.execute(SERVICE_BASELINE_SCHEMA)
    conn.execute(SYSTEM_BASELINE_SCHEMA)
    conn.execute(OBSERVATION_SCHEMA)
    conn.execute(RECOMMENDATION_SCHEMA)
    _ensure_column(conn, "recommendations", "updated_at", "TEXT")
    conn.execute("UPDATE recommendations SET updated_at = created_at WHERE updated_at IS NULL OR updated_at = ''")
    conn.commit()
    conn.close()


def safe_cleanup_old_rows():
    conn = connect()
    deleted = {}
    retention = [
        ("observations", "created_at", config.OBSERVATIONS_RETENTION_DAYS, None),
        ("worker_checks", "created_at", config.WORKER_CHECKS_RETENTION_DAYS, None),
        ("action_log", "created_at", config.ACTION_LOG_RETENTION_DAYS, None),
        ("incidents", "resolved_at", config.RESOLVED_INCIDENTS_RETENTION_DAYS, "resolved_at IS NOT NULL"),
    ]
    for table, column, days, extra_where in retention:
        cutoff = cutoff_iso(days)
        where = f"{column} < ?"
        if extra_where:
            where = f"{extra_where} AND {where}"
        cur = conn.execute(f"DELETE FROM {table} WHERE {where}", (cutoff,))
        deleted[table] = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


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
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=int(minutes))).isoformat()
    conn = connect()
    row = conn.execute(
        "SELECT COUNT(*) AS total FROM action_log WHERE action = ? AND target = ? AND status = 'error' AND created_at >= ?",
        (action, target, cutoff),
    ).fetchone()
    conn.close()
    return int(row["total"] if row else 0)
