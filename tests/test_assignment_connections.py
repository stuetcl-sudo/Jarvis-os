"""Assignment operations release SQLite handles without depending on GC."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import family_task_assignments as assignments


class AssignmentConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "assignments.db"
        connection = sqlite3.connect(self.path)
        try:
            with connection:
                connection.execute("CREATE TABLE auth_users (user_id TEXT PRIMARY KEY)")
                connection.execute("INSERT INTO auth_users VALUES ('person')")
        finally:
            connection.close()
        real_connect = sqlite3.connect
        self.opened = []

        def track(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            self.opened.append(connection)  # prevent GC masking a resource leak
            return connection

        self.patch = patch.object(assignments.sqlite3, "connect", track)
        self.patch.start()
        self.store = assignments.FamilyTaskAssignmentStore(self.path)

    def tearDown(self):
        self.patch.stop()
        for connection in self.opened:
            connection.close()
        self.temporary.cleanup()

    def assert_closed(self):
        self.assertTrue(self.opened)
        for connection in self.opened:
            with self.assertRaisesRegex(sqlite3.ProgrammingError, "closed"):
                connection.execute("SELECT 1")

    def test_get_closes_connections(self):
        self.assertIsNone(self.store.get("family", "task"))
        self.assert_closed()

    def test_get_many_closes_connections(self):
        self.store.get_many({("family", "task")})
        self.assert_closed()

    def test_set_commits_and_closes_connections(self):
        self.store.set("family", "task", "person")
        self.assertEqual(self.store.get("family", "task"), "person")
        self.assert_closed()

    def test_delete_closes_connections(self):
        self.store.set("family", "task", "person")
        self.store.delete("family", "task")
        self.assertIsNone(self.store.get("family", "task"))
        self.assert_closed()

    def test_prune_closes_connections(self):
        self.store.set("family", "task", "person")
        self.assertEqual(self.store.prune(set()), 1)
        self.assertIsNone(self.store.get("family", "task"))
        self.assert_closed()

    def test_failed_assignment_rolls_back_and_closes_connections(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.set("family", "task", "missing-person")
        self.assert_closed()
        self.assertIsNone(self.store.get("family", "task"))

    def test_installer_pending_request_read_closes_connections(self):
        from app import managed_home_assistant_installer as installer
        self.assertFalse(installer._has_pending_request(self.path))
        self.assert_closed()

    def test_installer_failure_write_commits_and_closes_connections(self):
        from app import managed_home_assistant_installer as installer
        from app import settings_store
        installer._set_failure("installer_interrupted", self.path)
        self.assertEqual(settings_store.get_setting(installer.STATE_SETTING, db_path=self.path), installer.FAILED)
        self.assert_closed()


if __name__ == "__main__":
    unittest.main()
