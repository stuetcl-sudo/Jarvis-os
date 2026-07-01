import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "scripts" / "validate_family_status.py"
SPEC = importlib.util.spec_from_file_location("validate_family_status", HELPER_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def assert_rejected(kind, payload):
    try:
        MODULE.validate_status(kind, payload)
    except ValueError:
        return
    raise AssertionError("invalid family status payload was accepted")


def test_supported_weather_statuses():
    assert MODULE.validate_status("weather", {"status": "ok"}) == "ok"
    assert MODULE.validate_status("weather", {"status": "not_configured"}) == "not_configured"
    assert MODULE.validate_status("weather", {"status": "stale"}) == "stale"
    assert MODULE.validate_status("weather", {"status": "unavailable"}) == "unavailable"
    assert_rejected("weather", {"status": "unknown"})
    assert_rejected("weather", {})


def test_supported_calendar_statuses():
    assert MODULE.validate_status("calendar", {"status": "partial"}) == "partial"
    assert MODULE.validate_status("calendar", {"status": "not_configured"}) == "not_configured"
    assert MODULE.validate_status("calendar", {"status": "ok"}) == "ok"
    assert MODULE.validate_status("calendar", {"status": "stale"}) == "stale"
    assert MODULE.validate_status("calendar", {"status": "unavailable"}) == "unavailable"
    assert_rejected("calendar", {"status": "unknown"})
    assert_rejected("calendar", [])


def test_malformed_json_fails():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "response.json"
        path.write_text("not-json", encoding="utf-8")
        try:
            MODULE.load_payload(path)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed JSON was accepted")

        path.write_text(json.dumps({"status": "ok"}), encoding="utf-8")
        assert MODULE.load_payload(path) == {"status": "ok"}


if __name__ == "__main__":
    for test in [
        test_supported_weather_statuses,
        test_supported_calendar_statuses,
        test_malformed_json_fails,
    ]:
        test()
    print("Live family status validation tests OK")
