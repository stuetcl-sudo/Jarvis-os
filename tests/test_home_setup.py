import os
import tempfile

from app import home_setup


def test_home_settings_round_trip_and_completion():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        saved = home_setup.save_home_settings(
            "Mit hjem",
            "Europe/Copenhagen",
            "Ejer",
            db_path=db_path,
        )
        assert saved["home_name"] == "Mit hjem"
        assert saved["completed"] is False
        summary = home_setup.setup_summary(db_path=db_path)
        assert summary["ready_to_complete"] is True
        completed = home_setup.complete_setup(db_path=db_path)
        assert completed["completed"] is True


def test_invalid_timezone_is_rejected():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        try:
            home_setup.save_home_settings("Hjem", "Invalid/Timezone", "Ejer", db_path=db_path)
        except ValueError as exc:
            assert "Tidszonen" in str(exc)
        else:
            raise AssertionError("Invalid timezone was accepted")


def test_completion_requires_home_details():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        try:
            home_setup.complete_setup(db_path=db_path)
        except ValueError:
            return
        raise AssertionError("Incomplete setup was completed")


def test():
    test_home_settings_round_trip_and_completion()
    test_invalid_timezone_is_rejected()
    test_completion_requires_home_details()
    print("Home setup tests OK")


if __name__ == "__main__":
    test()
