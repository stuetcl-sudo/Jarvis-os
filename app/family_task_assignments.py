import sqlite3
import threading
from datetime import datetime, timezone

from app import config

_TABLE_NAME = "family_task_assignments"
_initialize_lock = threading.Lock()
_initialized_paths = set()


def _database_path(db_path=None):
    return db_path or config.DB_PATH


def _connect(db_path=None):
    connection = sqlite3.connect(_database_path(db_path), timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def initialize_family_task_assignment_table(db_path=None):
    path = _database_path(db_path)

    with _initialize_lock:
        if path in _initialized_paths:
            return

        with _connect(path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS family_task_assignments (
                    list_key TEXT NOT NULL,
                    item_uid TEXT NOT NULL,
                    assignee_id TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (list_key, item_uid),
                    FOREIGN KEY (assignee_id)
                        REFERENCES auth_users(user_id)
                        ON DELETE SET NULL
                )
                """
            )

        _initialized_paths.add(path)


class FamilyTaskAssignmentStore:
    def __init__(self, db_path=None):
        self.db_path = _database_path(db_path)

    def _initialize(self):
        initialize_family_task_assignment_table(self.db_path)

    def get(self, list_key, item_uid):
        self._initialize()

        with _connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT assignee_id
                FROM family_task_assignments
                WHERE list_key = ? AND item_uid = ?
                """,
                (list_key, item_uid),
            ).fetchone()

        return row["assignee_id"] if row is not None else None

    def get_many(self, task_keys):
        self._initialize()

        normalized = {
            (str(list_key).strip(), str(item_uid).strip())
            for list_key, item_uid in task_keys
            if str(list_key).strip() and str(item_uid).strip()
        }
        if not normalized:
            return {}

        result = {}
        with _connect(self.db_path) as connection:
            for list_key, item_uid in normalized:
                row = connection.execute(
                    """
                    SELECT assignee_id
                    FROM family_task_assignments
                    WHERE list_key = ? AND item_uid = ?
                    """,
                    (list_key, item_uid),
                ).fetchone()
                if row is not None:
                    result[(list_key, item_uid)] = row["assignee_id"]

        return result

    def set(self, list_key, item_uid, assignee_id):
        self._initialize()

        clean_list_key = str(list_key or "").strip()
        clean_item_uid = str(item_uid or "").strip()
        clean_assignee_id = str(assignee_id or "").strip() or None

        if not clean_list_key or not clean_item_uid:
            raise ValueError("Task assignment key is invalid")

        with _connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO family_task_assignments (
                    list_key,
                    item_uid,
                    assignee_id,
                    updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(list_key, item_uid)
                DO UPDATE SET
                    assignee_id = excluded.assignee_id,
                    updated_at = excluded.updated_at
                """,
                (
                    clean_list_key,
                    clean_item_uid,
                    clean_assignee_id,
                    _now_iso(),
                ),
            )

        return clean_assignee_id

    def delete(self, list_key, item_uid):
        self._initialize()

        with _connect(self.db_path) as connection:
            connection.execute(
                """
                DELETE FROM family_task_assignments
                WHERE list_key = ? AND item_uid = ?
                """,
                (str(list_key).strip(), str(item_uid).strip()),
            )

    def prune(self, active_task_keys):
        self._initialize()

        active = {
            (str(list_key).strip(), str(item_uid).strip())
            for list_key, item_uid in active_task_keys
            if str(list_key).strip() and str(item_uid).strip()
        }

        removed = 0
        with _connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT list_key, item_uid
                FROM family_task_assignments
                """
            ).fetchall()

            for row in rows:
                key = (row["list_key"], row["item_uid"])
                if key in active:
                    continue
                connection.execute(
                    """
                    DELETE FROM family_task_assignments
                    WHERE list_key = ? AND item_uid = ?
                    """,
                    key,
                )
                removed += 1

        return removed
