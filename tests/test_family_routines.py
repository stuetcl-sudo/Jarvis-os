import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app import routines as routines_module
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.main_auth import app
from app.routines import MORNING_TASKS, RoutineStore, local_now, routine_tasks

WEDNESDAY = datetime.fromisoformat("2026-07-01T09:00:00+02:00")
SUNDAY = datetime.fromisoformat("2026-07-05T19:00:00+02:00")
MONDAY = datetime.fromisoformat("2026-07-06T19:00:00+02:00")
APPROVED_SVG_NAMESPACES = (
    "http://www.w3.org/2000/svg",
    "http://www.w3.org/1999/xlink",
    "http://www.w3.org/XML/1998/namespace",
)


@contextmanager
def routine_environment(now=WEDNESDAY):
    previous_db = config.DB_PATH
    previous_store = routines_module.routine_store
    previous_timezone = os.environ.get("ROUTINE_TIMEZONE")
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "routines.db")
        os.environ["ROUTINE_TIMEZONE"] = "Europe/Copenhagen"
        init_db()
        initialize_auth_tables()
        routines_module.routine_store = RoutineStore(Path(folder) / "family_routines.json", lambda: now)
        client = TestClient(app, follow_redirects=False)
        try:
            yield client, routines_module.routine_store, Path(folder)
        finally:
            client.close()
            routines_module.routine_store = previous_store
            config.DB_PATH = previous_db
            if previous_timezone is None:
                os.environ.pop("ROUTINE_TIMEZONE", None)
            else:
                os.environ["ROUTINE_TIMEZONE"] = previous_timezone


def login(client, role):
    username = f"routine-{role}"
    credential = "".join(["Routine", "Role", "Pass", "-42!"])
    auth_service.create_user(username, f"Routine {role}", role, credential)
    response = client.post("/api/auth/login", json={"username": username, "password": credential})
    assert response.status_code == 200, response.text
    profile = client.get("/api/auth/me")
    assert profile.status_code == 200
    return profile.json()["csrf_token"]


def assert_svg_uses_local_resources(svg_text):
    without_namespaces = svg_text
    for namespace in APPROVED_SVG_NAMESPACES:
        without_namespaces = without_namespaces.replace(namespace, "")
    assert not re.search(r"https?://", without_namespaces, re.IGNORECASE)
    assert not re.search(
        r"(?:href|xlink:href)\s*=\s*[\"']\s*https?://",
        svg_text,
        re.IGNORECASE,
    )
    assert not re.search(
        r"@import\s+(?:url\(\s*)?[\"']?\s*https?://",
        svg_text,
        re.IGNORECASE,
    )


def assert_svg_rejected(svg_text):
    try:
        assert_svg_uses_local_resources(svg_text)
    except AssertionError:
        return
    raise AssertionError("remote SVG resource was accepted")


def test_fixed_routine_definitions_bath_days_and_timezone():
    assert [task.title for task in MORNING_TASKS] == [
        "Vågne op", "Se lidt TV", "Spise morgenmad", "Tage tøj på",
        "Børste tænder", "Spille lidt på iPad", "Tage overtøj på", "Gå i skole",
    ]
    normal = [task.title for task in routine_tasks("evening", MONDAY.date())]
    assert normal == [
        "Lektier", "Øvelser og træning", "Fri leg", "Spise aftensmad",
        "Rydde af bordet", "Fri leg", "Børste tænder", "Tage tøj af",
        "Lægge beskidt tøj i vasketøjskurven", "Gå i seng",
        "Høre musik eller lydbog", "Sove",
    ]
    for current in [WEDNESDAY, SUNDAY]:
        titles = [task.title for task in routine_tasks("evening", current.date())]
        cleanup = titles.index("Rydde af bordet")
        assert titles[cleanup + 1] == "Gå i bad"
        assert len(titles) == 13
    assert "Gå i bad" not in normal
    previous = os.environ.get("ROUTINE_TIMEZONE")
    try:
        os.environ["ROUTINE_TIMEZONE"] = "Europe/Copenhagen"
        converted = local_now(datetime.fromisoformat("2026-06-30T22:30:00+00:00"))
        assert converted.date().isoformat() == "2026-07-01"
    finally:
        if previous is None:
            os.environ.pop("ROUTINE_TIMEZONE", None)
        else:
            os.environ["ROUTINE_TIMEZONE"] = previous


def test_missing_malformed_atomic_and_separate_state():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "state.json"
        store = RoutineStore(path, lambda: WEDNESDAY)
        initial = store.snapshot()
        assert path.exists()
        assert initial["routines"]["morning"]["current_index"] == 0
        path.write_text("not-json", encoding="utf-8")
        reset = store.snapshot()
        assert reset["routines"]["evening"]["current_index"] == 0
        morning = store.change("morning", "complete", 0)
        assert morning["routines"]["morning"]["current_index"] == 1
        assert morning["routines"]["evening"]["current_index"] == 0
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert parsed["morning"]["current_index"] == 1
        assert not list(Path(folder).glob("*.tmp"))


def test_complete_back_reset_final_and_duplicate_safety():
    with tempfile.TemporaryDirectory() as folder:
        store = RoutineStore(Path(folder) / "state.json", lambda: WEDNESDAY)
        first = store.change("morning", "complete", 0)
        duplicate = store.change("morning", "complete", 0)
        assert first["routines"]["morning"]["current_index"] == 1
        assert duplicate["routines"]["morning"]["current_index"] == 1
        back = store.change("morning", "back", 1)
        assert back["routines"]["morning"]["current_index"] == 0
        assert store.change("morning", "back", 0)["routines"]["morning"]["current_index"] == 0
        for index in range(len(MORNING_TASKS)):
            store.change("morning", "complete", index)
        completed = store.snapshot()["routines"]["morning"]
        assert completed["completed"] is True
        assert completed["current_task"] is None
        assert store.change("morning", "complete", len(MORNING_TASKS))["routines"]["morning"]["completed"] is True
        store.change("evening", "complete", 0)
        reset = store.change("morning", "reset")
        assert reset["routines"]["morning"]["current_index"] == 0
        assert reset["routines"]["evening"]["current_index"] == 1


def test_new_date_and_concurrent_updates_reset_safely():
    clock = [WEDNESDAY]
    with tempfile.TemporaryDirectory() as folder:
        store = RoutineStore(Path(folder) / "state.json", lambda: clock[0])
        store.change("morning", "complete", 0)
        clock[0] = datetime.fromisoformat("2026-07-02T08:00:00+02:00")
        assert store.snapshot()["routines"]["morning"]["current_index"] == 0
        results = []
        threads = [threading.Thread(target=lambda: results.append(store.change("morning", "complete", 0))) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
        assert len(results) == 6
        assert store.snapshot()["routines"]["morning"]["current_index"] == 1


def test_anonymous_and_authenticated_role_api_behavior():
    with routine_environment() as (client, _, _):
        anonymous = client.get("/api/family/routines?role=owner")
        assert anonymous.status_code == 200
        assert anonymous.json() == {"status": "authentication_required", "routines": []}
        assert client.post("/api/family/routines/morning/complete", json={"expected_index": 0}).status_code == 401

    for role in ["owner", "adult", "child", "wall_display"]:
        with routine_environment() as (client, _, _):
            csrf = login(client, role)
            if role == "owner":
                auth_service.create_user(
                    "routine-child", "Routine Child", "child", "Routine-Child-Pass-42!"
                )
            response = client.get("/api/family/routines?role=anonymous")
            assert response.status_code == 200
            assert response.json()["routines"]["morning"]["current_task"]["title"] == "Vågne op"
            missing = client.post("/api/family/routines/morning/complete", json={"expected_index": 0})
            assert missing.status_code == 403
            invalid = client.post(
                "/api/family/routines/morning/complete",
                headers={"X-CSRF-Token": "invalid"},
                json={"expected_index": 0},
            )
            assert invalid.status_code == 403
            complete = client.post(
                "/api/family/routines/morning/complete",
                headers={"X-CSRF-Token": csrf},
                json={"expected_index": 0},
            )
            assert complete.status_code == 200
            assert complete.json()["routines"]["morning"]["current_index"] == 1
            unknown = client.post(
                "/api/family/routines/unknown/complete",
                headers={"X-CSRF-Token": csrf},
                json={"expected_index": 0},
            )
            assert unknown.status_code == 404


def test_existing_owner_only_write_protection_is_unchanged_without_execution():
    with routine_environment() as (client, _, _):
        csrf = login(client, "adult")
        response = client.post("/api/worker/run-once", headers={"X-CSRF-Token": csrf})
        assert response.status_code == 403
    middleware = (Path(__file__).resolve().parents[1] / "app/main_auth.py").read_text()
    assert 'if current_user["role"] != "owner"' in middleware
    assert "and not routine_write" in middleware


def test_svg_network_reference_guard():
    standard = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'xml:base="http://www.w3.org/XML/1998/namespace"></svg>'
    )
    assert_svg_uses_local_resources(standard)

    remote_base = "https://" + "assets.invalid/"
    assert_svg_rejected(
        '<svg xmlns="http://www.w3.org/2000/svg"><image href="'
        + remote_base
        + 'image.svg"/></svg>'
    )
    assert_svg_rejected(
        '<svg xmlns="http://www.w3.org/2000/svg"><use xlink:href="'
        + remote_base
        + 'icons.svg#task"/></svg>'
    )
    assert_svg_rejected(
        '<svg xmlns="http://www.w3.org/2000/svg"><style>@import url("'
        + remote_base
        + 'icons.css");</style></svg>'
    )
    assert_svg_rejected(
        '<svg xmlns="http://www.w3.org/2000/svg"><desc>'
        + remote_base
        + 'arbitrary</desc></svg>'
    )


def test_frontend_is_local_safe_and_one_task_at_a_time():
    root = Path(__file__).resolve().parents[1]
    javascript = (root / "app/static/js/routines.js").read_text()
    family_javascript = (root / "app/static/js/family.js").read_text()
    stylesheet = (root / "app/static/css/routines.css").read_text()
    template = (root / "app/static/index.html").read_text()
    pictograms = (root / "app/static/pictograms/routines.svg").read_text()
    assert 'data-family-card="routine"' in template
    assert template.count('id="routineTitle"') == 1
    assert "Godt klaret!" in javascript
    assert "textContent" in javascript and "innerHTML" not in javascript
    assert "localStorage" not in javascript and "sessionStorage" not in javascript
    assert "localStorage" not in family_javascript and "sessionStorage" not in family_javascript
    assert "routineEndpoints" in javascript
    assert "button.disabled = busy" in javascript
    assert_svg_uses_local_resources(pictograms)
    assert "base64" not in pictograms
    assert 'body[data-family-role="child"] .routine-card' in stylesheet
    assert 'body[data-family-role="wall_display"] .routine-card' in stylesheet
    assert "min-height: 44px" in stylesheet


if __name__ == "__main__":
    for test in [
        test_fixed_routine_definitions_bath_days_and_timezone,
        test_missing_malformed_atomic_and_separate_state,
        test_complete_back_reset_final_and_duplicate_safety,
        test_new_date_and_concurrent_updates_reset_safely,
        test_anonymous_and_authenticated_role_api_behavior,
        test_existing_owner_only_write_protection_is_unchanged_without_execution,
        test_svg_network_reference_guard,
        test_frontend_is_local_safe_and_one_task_at_a_time,
    ]:
        test()
    print("Family routine tests OK")
