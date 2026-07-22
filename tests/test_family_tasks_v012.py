import os
from pathlib import Path
import sqlite3
import tempfile

from app import config
from app.family_task_assignments import FamilyTaskAssignmentStore
from app.family_tasks import (
    EDITOR_ROLES,
    FamilyTasksService,
    HomeAssistantTasksClient,
    TaskSource,
    FamilyTasksSettings,
    parse_task_sources,
)
from app.home_assistant import HomeAssistantConnection

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
TASKS_JS = (ROOT / "app/static/js/family-tasks.js").read_text(encoding="utf-8")
TASKS_CSS = (ROOT / "app/static/css/family-tasks.css").read_text(encoding="utf-8")
MAIN_AUTH = (ROOT / "app/main_auth.py").read_text(encoding="utf-8")
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
TASKS_MODULE = (ROOT / "app/family_tasks.py").read_text(encoding="utf-8")


class FakeResponse:
    is_success = True

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeHttpClient:
    payloads = {}
    requests = []

    def __init__(self, headers=None, timeout=None):
        self.headers = headers
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def request(self, method, url, params=None, json=None):
        self.__class__.requests.append((method, url, params, json))
        if url.endswith("/api/services/todo/get_items"):
            return FakeResponse(self.__class__.payloads[json["entity_id"]])
        return FakeResponse([])


class FakeSettingsLoader:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def settings():
    return FamilyTasksSettings(
        connection=HomeAssistantConnection("http://home-assistant:8123", "secret", 5),
        sources=(
            TaskSource("todo.familieopgaver", "familieopgaver", "Familieopgaver"),
            TaskSource("todo.lektier", "lektier", "Lektier"),
            TaskSource("todo.shopping_list", "shopping-list", "Indkøbsliste"),
        ),
        cache_seconds=60,
        stale_seconds=900,
        max_items=30,
    )


def task_payloads():
    result = {}
    for entity_id, items in {
        "todo.familieopgaver": [
            {"summary": "Tøm opvaskemaskinen", "uid": "family-1", "status": "needs_action"},
            {"summary": "Allerede færdig", "uid": "family-2", "status": "completed"},
        ],
        "todo.lektier": [
            {
                "summary": "Matematik",
                "uid": "homework-1",
                "status": "needs_action",
                "due": "2026-07-03",
                "description": "Side 12 og 13",
            }
        ],
        "todo.shopping_list": [
            {"summary": "Mælk", "uid": "shopping-1", "status": "needs_action"}
        ],
    }.items():
        result[entity_id] = {
            "changed_states": [],
            "service_response": {entity_id: {"items": items}},
        }
    return result


def create_assignment_test_database(path):
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE auth_users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            disabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_login_at TEXT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO auth_users (
            user_id,
            username,
            display_name,
            role,
            password_hash,
            disabled,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            "person-dennis",
            "dennis",
            "Dennis",
            "owner",
            "test",
            "2026-07-22T00:00:00+00:00",
            "2026-07-22T00:00:00+00:00",
        ),
    )
    connection.commit()
    connection.close()


def test_task_assignment_store_defaults_to_family_and_isolated_by_task():
    with tempfile.TemporaryDirectory() as folder:
        db_path = Path(folder) / "jarvis.db"
        create_assignment_test_database(db_path)
        store = FamilyTaskAssignmentStore(db_path)

        assert store.get("familieopgaver", "task-1") is None

        store.set("familieopgaver", "task-1", "person-dennis")

        assert store.get("familieopgaver", "task-1") == "person-dennis"
        assert store.get("familieopgaver", "task-2") is None
        assert store.get("lektier", "task-1") is None

        store.set("familieopgaver", "task-1", None)

        assert store.get("familieopgaver", "task-1") is None


def test_task_assignment_store_reads_many_and_prunes_missing_tasks():
    with tempfile.TemporaryDirectory() as folder:
        db_path = Path(folder) / "jarvis.db"
        create_assignment_test_database(db_path)
        store = FamilyTaskAssignmentStore(db_path)

        store.set("familieopgaver", "task-1", "person-dennis")
        store.set("familieopgaver", "task-2", None)
        store.set("lektier", "task-3", "person-dennis")

        assignments = store.get_many(
            [
                ("familieopgaver", "task-1"),
                ("familieopgaver", "task-2"),
                ("missing", "task-4"),
            ]
        )

        assert assignments == {
            ("familieopgaver", "task-1"): "person-dennis",
            ("familieopgaver", "task-2"): None,
        }

        removed = store.prune(
            {
                ("familieopgaver", "task-1"),
                ("familieopgaver", "task-2"),
            }
        )

        assert removed == 1
        assert store.get("lektier", "task-3") is None

        store.delete("familieopgaver", "task-1")
        assert store.get("familieopgaver", "task-1") is None



def test_default_task_entities_include_shopping_list():
    previous = os.environ.pop("HOME_ASSISTANT_TASK_LISTS", None)
    try:
        assert config.family_tasks_configuration()["sources"] == (
            "todo.familieopgaver|Familieopgaver,todo.lektier|Lektier,"
            "todo.shopping_list|Indkøbsliste"
        )
        assert config.family_tasks_configuration()["max_items"] == 30
    finally:
        if previous is not None:
            os.environ["HOME_ASSISTANT_TASK_LISTS"] = previous
    assert "todo.shopping_list|Indkøbsliste" in ENV_EXAMPLE


def test_task_source_parser_accepts_three_plain_todo_entities():
    sources = parse_task_sources(
        "todo.familieopgaver|Familieopgaver,todo.lektier|Lektier,todo.shopping_list|Indkøbsliste"
    )
    assert [(source.entity_id, source.key, source.label) for source in sources] == [
        ("todo.familieopgaver", "familieopgaver", "Familieopgaver"),
        ("todo.lektier", "lektier", "Lektier"),
        ("todo.shopping_list", "shopping-list", "Indkøbsliste"),
    ]


def test_client_reads_all_lists_and_filters_completed_items():
    FakeHttpClient.requests = []
    FakeHttpClient.payloads = task_payloads()
    lists, failures = HomeAssistantTasksClient(settings(), FakeHttpClient).fetch()
    assert failures == 0
    assert [item["key"] for item in lists] == ["familieopgaver", "lektier", "shopping-list"]
    assert [item["summary"] for item in lists[0]["items"]] == ["Tøm opvaskemaskinen"]
    assert lists[1]["items"][0]["description"] == "Side 12 og 13"
    assert lists[2]["items"][0]["summary"] == "Mælk"
    assert all(request[1].endswith("/api/services/todo/get_items") for request in FakeHttpClient.requests)


def test_client_uses_only_controlled_todo_service_calls():
    client = HomeAssistantTasksClient(settings(), FakeHttpClient)
    source = settings().sources[2]
    FakeHttpClient.requests = []
    client.complete(source, "shopping-1")
    client.add(source, "Brød", "Rugbrød")
    client.update(source, "shopping-1", "Letmælk", "To liter")
    client.remove(source, "shopping-1")
    assert [request[1].rsplit("/", 1)[-1] for request in FakeHttpClient.requests] == [
        "update_item",
        "add_item",
        "update_item",
        "remove_item",
    ]
    assert FakeHttpClient.requests[0][3] == {
        "entity_id": "todo.shopping_list",
        "item": "shopping-1",
        "status": "completed",
    }
    assert FakeHttpClient.requests[1][3] == {
        "entity_id": "todo.shopping_list",
        "item": "Brød",
        "description": "Rugbrød",
    }
    assert FakeHttpClient.requests[2][3]["rename"] == "Letmælk"
    assert FakeHttpClient.requests[3][3] == {
        "entity_id": "todo.shopping_list",
        "item": "shopping-1",
    }


class FakeAssignmentStore:
    def __init__(self, assignments=None):
        self.assignments = assignments or {}

    def get_many(self, task_keys):
        return {
            key: self.assignments[key]
            for key in task_keys
            if key in self.assignments
        }


def family_people():
    return [
        {
            "user_id": "person-liam",
            "display_name": "Liam",
            "role": "child",
        },
        {
            "user_id": "person-dennis",
            "display_name": "Dennis",
            "role": "owner",
        },
    ]


def test_task_api_adds_people_counts_and_family_defaults():
    FakeHttpClient.payloads = task_payloads()

    service = FamilyTasksService(
        settings_loader=FakeSettingsLoader(settings()),
        client_factory=FakeHttpClient,
        monotonic=lambda: 1.0,
        assignment_store=FakeAssignmentStore(
            {
                ("familieopgaver", "family-1"): "person-dennis",
                ("lektier", "homework-1"): "disabled-or-missing-person",
            }
        ),
        people_loader=family_people,
    )

    result = service.get_tasks({"role": "owner"})

    assert result["status"] == "ok"
    assert result["people"] == [
        {
            "user_id": None,
            "display_name": "Familien",
            "role": "family",
            "count": 2,
        },
        {
            "user_id": "person-liam",
            "display_name": "Liam",
            "role": "child",
            "count": 0,
        },
        {
            "user_id": "person-dennis",
            "display_name": "Dennis",
            "role": "owner",
            "count": 1,
        },
    ]

    items = {
        (task_list["key"], item["uid"]): item
        for task_list in result["lists"]
        for item in task_list["items"]
    }

    assert items[("familieopgaver", "family-1")]["assignee_id"] == "person-dennis"
    assert items[("lektier", "homework-1")]["assignee_id"] is None
    assert items[("shopping-list", "shopping-1")]["assignee_id"] is None


def test_task_api_hides_people_from_anonymous_users():
    FakeHttpClient.payloads = task_payloads()

    service = FamilyTasksService(
        settings_loader=FakeSettingsLoader(settings()),
        client_factory=FakeHttpClient,
        monotonic=lambda: 1.0,
        assignment_store=FakeAssignmentStore(),
        people_loader=family_people,
    )

    result = service.get_tasks(None)

    assert result["status"] == "authentication_required"
    assert result["people"] == []
    assert result["lists"] == []



def test_permissions_allow_completion_for_family_but_editing_for_adults_only():
    assert EDITOR_ROLES == {"owner", "adult"}
    FakeHttpClient.payloads = task_payloads()
    service = FamilyTasksService(
        settings_loader=FakeSettingsLoader(settings()),
        client_factory=FakeHttpClient,
        monotonic=lambda: 1.0,
        assignment_store=FakeAssignmentStore(),
        people_loader=family_people,
    )
    anonymous = service.get_tasks(None)
    assert anonymous["status"] == "authentication_required"
    assert anonymous["can_edit"] is False
    child = service.get_tasks({"role": "child"})
    assert child["can_edit"] is False
    owner = service.get_tasks({"role": "owner"})
    assert owner["can_edit"] is True
    for role in [None, {"role": "child"}, {"role": "wall_display"}]:
        try:
            service.add_task("shopping-list", "Brød", None, role)
        except PermissionError:
            pass
        else:
            raise AssertionError("Non-adult task editing must be rejected")


def test_frontend_supports_shopping_add_edit_remove_and_safe_completion():
    assert 'data-family-card="tasks"' in INDEX
    assert '/static/js/family-tasks.js' in INDEX
    assert 'input.placeholder = isShoppingList(taskList)' in TASKS_JS
    assert '"Tilføj en vare"' in TASKS_JS
    assert '"Tilføj et punkt"' in TASKS_JS
    assert 'method,' in TASKS_JS
    for method in ["POST", "PUT", "DELETE"]:
        assert f'"{method}"' in TASKS_JS
    assert 'credentials: "same-origin"' in TASKS_JS
    assert '"X-CSRF-Token": csrfToken' in TASKS_JS
    assert "window.prompt" in TASKS_JS
    assert "window.confirm" in TASKS_JS
    assert "replaceChildren" in TASKS_JS
    assert "function showTaskRefreshFailure()" in TASKS_JS
    assert 'setTaskNotice("Viser senest hentede familielister")' in TASKS_JS
    for forbidden in ["innerHTML", "insertAdjacentHTML", "localStorage", "sessionStorage", "eval("]:
        assert forbidden not in TASKS_JS
    assert ".family-task-add" in TASKS_CSS
    assert ".family-task-actions" in TASKS_CSS
    assert ".family-task-list-shopping-list" in TASKS_CSS


def test_router_and_middleware_protect_controlled_family_writes():
    assert "family_task_write = (" in MAIN_AUTH
    assert 'request.method in {"POST", "PUT", "DELETE"}' in MAIN_AUTH
    assert 'path.startswith("/api/family/tasks/")' in MAIN_AUTH
    assert 'family_feature_hidden(current_user, "tasks")' in MAIN_AUTH
    assert 'request.headers.get("X-CSRF-Token", "")' in MAIN_AUTH

    assert "def _can_perform(current_user, action):" in TASKS_MODULE
    assert "role_can_do(role, action)" in TASKS_MODULE
    for action in ["task_complete", "task_add", "task_edit", "task_remove"]:
        assert f'"{action}"' in TASKS_MODULE

    for route in [
        '@router.post("/api/family/tasks/{list_key}/complete")',
        '@router.post("/api/family/tasks/{list_key}/items")',
        '@router.put("/api/family/tasks/{list_key}/items")',
        '@router.delete("/api/family/tasks/{list_key}/items")',
    ]:
        assert route in TASKS_MODULE

    for service in ["todo/add_item", "todo/update_item", "todo/remove_item"]:
        assert f'"/api/services/{service}"' in TASKS_MODULE


if __name__ == "__main__":
    for test in [
        test_task_assignment_store_defaults_to_family_and_isolated_by_task,
        test_task_assignment_store_reads_many_and_prunes_missing_tasks,
        test_default_task_entities_include_shopping_list,
        test_task_source_parser_accepts_three_plain_todo_entities,
        test_client_reads_all_lists_and_filters_completed_items,
        test_client_uses_only_controlled_todo_service_calls,
        test_task_api_adds_people_counts_and_family_defaults,
        test_task_api_hides_people_from_anonymous_users,
        test_permissions_allow_completion_for_family_but_editing_for_adults_only,
        test_frontend_supports_shopping_add_edit_remove_and_safe_completion,
        test_router_and_middleware_protect_controlled_family_writes,
    ]:
        test()
    print("Family tasks v0.13 tests OK")
