import copy
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app import routines as routines_module
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.family_view import render_family_page
from app.main_auth import app
from app.routine_definitions import (
    DEFAULT_DEFINITIONS,
    MAX_TASKS,
    DefinitionValidationError,
    RoutineDefinitionStore,
    definition_to_dict,
    tasks_for_date,
    validate_definition,
)
from app.routines import RoutineStore

FIXED_NOW = datetime.fromisoformat("2026-07-01T17:00:00+02:00")
MONDAY = datetime.fromisoformat("2026-07-06T17:00:00+02:00")
SVG_NAMESPACE = "http://www.w3.org/2000/svg"


@contextmanager
def editor_environment(now=FIXED_NOW):
    previous_db = config.DB_PATH
    previous_definitions = routines_module.definition_store
    previous_progress = routines_module.routine_store
    previous_timezone = os.environ.get("ROUTINE_TIMEZONE")
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        config.DB_PATH = str(root / "editor.db")
        os.environ["ROUTINE_TIMEZONE"] = "Europe/Copenhagen"
        init_db()
        initialize_auth_tables()
        definitions = RoutineDefinitionStore(root / "family_routine_definitions.json")
        progress = RoutineStore(root / "family_routines.json", lambda: now, definitions)
        routines_module.definition_store = definitions
        routines_module.routine_store = progress
        client = TestClient(app, follow_redirects=False)
        try:
            yield client, definitions, progress, root
        finally:
            client.close()
            routines_module.definition_store = previous_definitions
            routines_module.routine_store = previous_progress
            config.DB_PATH = previous_db
            if previous_timezone is None:
                os.environ.pop("ROUTINE_TIMEZONE", None)
            else:
                os.environ["ROUTINE_TIMEZONE"] = previous_timezone


def login(client, role):
    username = f"editor-{role}"
    credential = "".join(["Editor", "Role", "Pass", "-42!"])
    auth_service.create_user(username, f"Editor {role}", role, credential)
    response = client.post("/api/auth/login", json={"username": username, "password": credential})
    assert response.status_code == 200, response.text
    profile = client.get("/api/auth/me")
    assert profile.status_code == 200
    return profile.json()["csrf_token"]


def default_payload(routine_id):
    return definition_to_dict(DEFAULT_DEFINITIONS[routine_id])


def test_definition_store_defaults_malformed_custom_atomic_and_separate():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        path = root / "definitions.json"
        store = RoutineDefinitionStore(path)
        assert store.get("morning") == DEFAULT_DEFINITIONS["morning"]
        assert not path.exists()
        path.write_text("not-json", encoding="utf-8")
        assert store.get("evening") == DEFAULT_DEFINITIONS["evening"]
        custom = default_payload("morning")
        custom["label"] = "Ny morgen"
        custom["tasks"][0]["title"] = "Stå roligt op"
        previous, saved = store.update("morning", custom)
        assert previous.id == "morning"
        assert saved.label == "Ny morgen"
        assert store.get("morning").tasks[0].title == "Stå roligt op"
        assert store.get("evening") == DEFAULT_DEFINITIONS["evening"]
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored["version"] == 2
        assert stored["shared"]["morning"]["label"] == "Ny morgen"
        assert stored["persons"] == {}
        assert not list(root.glob("*.tmp"))
        assert RoutineDefinitionStore(path).get("morning").label == "Ny morgen"


def test_default_bath_and_weekday_filtering():
    evening = DEFAULT_DEFINITIONS["evening"]
    bath = next(task for task in evening.tasks if task.id == "evening_bath")
    cleanup_index = next(index for index, task in enumerate(evening.tasks) if task.id == "evening_cleanup")
    assert evening.tasks[cleanup_index + 1].id == "evening_bath"
    assert bath.weekdays == (2, 6)
    assert "evening_bath" in [task.id for task in tasks_for_date(evening, FIXED_NOW.date())]
    assert "evening_bath" not in [task.id for task in tasks_for_date(evening, MONDAY.date())]
    assert "evening_dinner" in [task.id for task in tasks_for_date(evening, MONDAY.date())]


def assert_invalid(payload):
    try:
        validate_definition("morning", payload)
    except DefinitionValidationError:
        return
    raise AssertionError("invalid routine definition was accepted")


def test_strict_definition_validation():
    valid = default_payload("morning")
    assert validate_definition("morning", valid).id == "morning"
    empty = copy.deepcopy(valid)
    empty["tasks"] = []
    assert_invalid(empty)
    excessive = copy.deepcopy(valid)
    excessive["tasks"] = [copy.deepcopy(valid["tasks"][0]) for _ in range(MAX_TASKS + 1)]
    for index, task in enumerate(excessive["tasks"]):
        task["id"] = f"morning_many_{index}"
    assert_invalid(excessive)
    cases = [
        ("title", "<script>alert(1)</script>"),
        ("title", "Se https://example.com"),
        ("pictogram", "remote-icon"),
        ("time", "25:99"),
        ("weekdays", [7]),
    ]
    for field, value in cases:
        payload = copy.deepcopy(valid)
        payload["tasks"][0][field] = value
        assert_invalid(payload)
    duplicate = copy.deepcopy(valid)
    duplicate["tasks"][1]["id"] = duplicate["tasks"][0]["id"]
    assert_invalid(duplicate)
    unknown = copy.deepcopy(valid)
    unknown["tasks"][0]["className"] = "danger"
    assert_invalid(unknown)
    try:
        validate_definition("unknown", valid)
    except KeyError:
        pass
    else:
        raise AssertionError("unknown routine ID accepted")


def test_progress_reconciliation_after_edits():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        definitions = RoutineDefinitionStore(root / "definitions.json")
        progress = RoutineStore(root / "progress.json", lambda: FIXED_NOW, definitions)
        progress.change("morning", "complete", 0)
        progress.change("morning", "complete", 1)
        assert progress.snapshot()["routines"]["morning"]["current_index"] == 2
        renamed = default_payload("morning")
        renamed["tasks"][1]["title"] = "Se roligt TV"
        definitions.update("morning", renamed)
        progress.reconcile_definition("morning")
        assert progress.snapshot()["routines"]["morning"]["current_index"] == 2
        removed = copy.deepcopy(renamed)
        removed["tasks"].pop(0)
        definitions.update("morning", removed)
        progress.reconcile_definition("morning")
        assert progress.snapshot()["routines"]["morning"]["current_index"] == 1
        added = copy.deepcopy(removed)
        added["tasks"].insert(0, {"title": "Nyt første trin", "pictogram": "wake", "time": None, "weekdays": []})
        definitions.update("morning", added)
        progress.reconcile_definition("morning")
        state = progress.snapshot()["routines"]["morning"]
        assert state["current_index"] == 0
        assert state["current_task"]["title"] == "Nyt første trin"
        reordered = default_payload("morning")
        reordered["tasks"][0], reordered["tasks"][1] = reordered["tasks"][1], reordered["tasks"][0]
        definitions.update("morning", reordered)
        progress.reconcile_definition("morning")
        assert progress.snapshot()["routines"]["morning"]["current_index"] == 0
        progress.change("evening", "complete", 0)
        definitions.reset_default("morning")
        progress.reconcile_definition("morning", reset=True)
        snapshot = progress.snapshot()["routines"]
        assert snapshot["morning"]["current_index"] == 0
        assert snapshot["evening"]["current_index"] == 1


def test_definition_api_authorization_csrf_and_updates():
    with editor_environment() as (client, _, _, _):
        assert client.get("/api/family/routines/definitions?role=owner").status_code == 401
        assert client.put("/api/family/routines/definitions/morning", json=default_payload("morning")).status_code == 401
    for role in ["child", "wall_display"]:
        with editor_environment() as (client, _, _, _):
            csrf = login(client, role)
            assert client.get("/api/family/routines/definitions?role=owner").status_code == 403
            denied = client.put(
                "/api/family/routines/definitions/morning",
                headers={"X-CSRF-Token": csrf},
                json=default_payload("morning"),
            )
            assert denied.status_code == 403
    for role in ["owner", "adult"]:
        with editor_environment() as (client, _, _, _):
            csrf = login(client, role)
            definitions = client.get("/api/family/routines/definitions")
            assert definitions.status_code == 200
            assert definitions.json()["routines"]["evening"]["tasks"][5]["weekdays"] == [2, 6]
            assert definitions.json()["pictograms"]
            assert client.put("/api/family/routines/definitions/morning", json=default_payload("morning")).status_code == 403
            invalid = client.put(
                "/api/family/routines/definitions/morning",
                headers={"X-CSRF-Token": "invalid"},
                json=default_payload("morning"),
            )
            assert invalid.status_code == 403
            payload = default_payload("morning")
            payload["tasks"][0]["title"] = "Vågne stille op"
            saved = client.put(
                "/api/family/routines/definitions/morning?role=child",
                headers={"X-CSRF-Token": csrf},
                json=payload,
            )
            assert saved.status_code == 200
            assert saved.json()["routines"]["morning"]["tasks"][0]["title"] == "Vågne stille op"
            reset = client.post(
                "/api/family/routines/definitions/morning/reset-default",
                headers={"X-CSRF-Token": csrf},
            )
            assert reset.status_code == 200
            assert reset.json()["routines"]["morning"]["tasks"][0]["title"] == "Vågne op"
            unknown = client.put(
                "/api/family/routines/definitions/unknown",
                headers={"X-CSRF-Token": csrf},
                json=payload,
            )
            assert unknown.status_code == 404


def test_person_specific_definitions_are_isolated():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        path = root / "definitions.json"
        store = RoutineDefinitionStore(path)

        dennis = "person-dennis"
        liam = "person-liam"

        dennis_payload = default_payload("morning")
        dennis_payload["label"] = "Dennis morgen"
        dennis_payload["tasks"][0]["title"] = "Dennis står op"

        previous, saved = store.update("morning", dennis_payload, person_id=dennis)
        assert previous == DEFAULT_DEFINITIONS["morning"]
        assert saved.label == "Dennis morgen"

        assert store.get("morning", dennis).label == "Dennis morgen"
        assert store.get("morning", dennis).tasks[0].title == "Dennis står op"

        assert store.get("morning", liam) == DEFAULT_DEFINITIONS["morning"]
        assert store.get("morning") == DEFAULT_DEFINITIONS["morning"]

        liam_payload = default_payload("evening")
        liam_payload["label"] = "Liam aften"
        liam_payload["tasks"][0]["title"] = "Liam laver lektier"

        store.update("evening", liam_payload, person_id=liam)

        assert store.get("evening", liam).label == "Liam aften"
        assert store.get("evening", dennis) == DEFAULT_DEFINITIONS["evening"]

        store.reset_default("morning", person_id=dennis)

        assert store.get("morning", dennis) == DEFAULT_DEFINITIONS["morning"]
        assert store.get("evening", liam).label == "Liam aften"

        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored["persons"][dennis]["morning"]["label"] == "Godmorgen-rutine"
        assert stored["persons"][liam]["evening"]["label"] == "Liam aften"



def test_existing_owner_only_writes_remain_unchanged():
    with editor_environment() as (client, _, _, _):
        csrf = login(client, "adult")
        assert client.post("/api/worker/run-once", headers={"X-CSRF-Token": csrf}).status_code == 403


def test_editor_frontend_role_rendering_and_security():
    root = Path(__file__).resolve().parents[1]
    javascript = (root / "app/static/js/routine-editor.js").read_text()
    stylesheet = (root / "app/static/css/routine-editor.css").read_text()
    assert 'id="routineEditButton"' in render_family_page({"role": "owner", "display_name": "Owner"})
    assert 'id="routineEditButton"' in render_family_page({"role": "adult", "display_name": "Adult"})
    assert 'id="routineEditButton"' not in render_family_page({"role": "child", "display_name": "Child"})
    assert 'id="routineEditButton"' not in render_family_page({"role": "wall_display", "display_name": "Wall"})
    assert "textContent" in javascript and "innerHTML" not in javascript
    assert "localStorage" not in javascript and "sessionStorage" not in javascript
    assert "eval(" not in javascript
    assert "editorEndpoints" in javascript
    assert "window.confirm" in javascript
    assert "Flyt op" in javascript and "Flyt ned" in javascript
    assert "element.disabled = pending" in javascript
    assert "/static/pictograms/routines.svg#" in javascript
    without_namespace = javascript.replace(SVG_NAMESPACE, "")
    assert "http://" not in without_namespace and "https://" not in without_namespace
    assert "min-height:44px" in stylesheet


if __name__ == "__main__":
    for test in [
        test_definition_store_defaults_malformed_custom_atomic_and_separate,
        test_default_bath_and_weekday_filtering,
        test_strict_definition_validation,
        test_progress_reconciliation_after_edits,
        test_definition_api_authorization_csrf_and_updates,
        test_person_specific_definitions_are_isolated,
        test_existing_owner_only_writes_remain_unchanged,
        test_editor_frontend_role_rendering_and_security,
    ]:
        test()
    print("Routine editor tests OK")
