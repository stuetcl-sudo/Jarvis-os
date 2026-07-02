import os
from pathlib import Path

from app import config
from app.family_tasks import (
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
        entity_id = json["entity_id"]
        self.__class__.requests.append((method, url, params, json))
        return FakeResponse(self.__class__.payloads[entity_id])


class FakeSettingsLoader:
    def __init__(self, settings):
        self.settings = settings

    def __call__(self):
        return self.settings


def settings():
    return FamilyTasksSettings(
        connection=HomeAssistantConnection("http://home-assistant:8123", "secret", 5),
        sources=(
            TaskSource("todo.familieopgaver", "familieopgaver", "Familieopgaver"),
            TaskSource("todo.lektier", "lektier", "Lektier"),
        ),
        cache_seconds=60,
        stale_seconds=900,
        max_items=20,
    )


def test_default_task_entities_match_confirmed_home_assistant_entities():
    previous = os.environ.pop("HOME_ASSISTANT_TASK_LISTS", None)
    try:
        assert config.family_tasks_configuration()["sources"] == (
            "todo.familieopgaver|Familieopgaver,todo.lektier|Lektier"
        )
    finally:
        if previous is not None:
            os.environ["HOME_ASSISTANT_TASK_LISTS"] = previous
    assert "HOME_ASSISTANT_TASK_LISTS=todo.familieopgaver|Familieopgaver,todo.lektier|Lektier" in ENV_EXAMPLE


def test_task_source_parser_accepts_only_plain_todo_entities():
    sources = parse_task_sources("todo.familieopgaver|Familieopgaver,todo.lektier|Lektier")
    assert [(source.entity_id, source.key, source.label) for source in sources] == [
        ("todo.familieopgaver", "familieopgaver", "Familieopgaver"),
        ("todo.lektier", "lektier", "Lektier"),
    ]


def test_home_assistant_tasks_client_uses_get_items_response_and_needs_action_only():
    FakeHttpClient.requests = []
    FakeHttpClient.payloads = {
        "todo.familieopgaver": {
            "changed_states": [],
            "service_response": {
                "todo.familieopgaver": {
                    "items": [
                        {"summary": "Tøm opvaskemaskinen", "uid": "family-1", "status": "needs_action"},
                        {"summary": "Allerede færdig", "uid": "family-2", "status": "completed"},
                    ]
                }
            },
        },
        "todo.lektier": {
            "changed_states": [],
            "service_response": {
                "todo.lektier": {
                    "items": [
                        {
                            "summary": "Matematik",
                            "uid": "homework-1",
                            "status": "needs_action",
                            "due": "2026-07-03",
                            "description": "Side 12 og 13",
                        }
                    ]
                }
            },
        },
    }

    lists, failures = HomeAssistantTasksClient(settings(), FakeHttpClient).fetch()
    assert failures == 0
    assert [task_list["key"] for task_list in lists] == ["familieopgaver", "lektier"]
    assert [item["summary"] for item in lists[0]["items"]] == ["Tøm opvaskemaskinen"]
    assert lists[1]["items"][0]["due"] == "2026-07-03"
    assert lists[1]["items"][0]["description"] == "Side 12 og 13"
    assert all(request[0] == "POST" for request in FakeHttpClient.requests)
    assert all(request[1].endswith("/api/services/todo/get_items") for request in FakeHttpClient.requests)
    assert all(request[2] == {"return_response": ""} for request in FakeHttpClient.requests)
    assert all(request[3]["status"] == "needs_action" for request in FakeHttpClient.requests)


def test_family_tasks_service_hides_private_lists_without_login():
    service = FamilyTasksService(
        settings_loader=FakeSettingsLoader(settings()),
        client_factory=FakeHttpClient,
        monotonic=lambda: 1.0,
    )
    result = service.get_tasks(None)
    assert result == {
        "status": "authentication_required",
        "lists": [],
        "total": 0,
        "unavailable_lists": 0,
        "stale": False,
    }


def test_family_dashboard_replaces_task_placeholder_safely():
    assert 'data-family-card="tasks"' in INDEX
    assert 'id="familyTaskLists"' in INDEX
    assert '/static/css/family-tasks.css' in INDEX
    assert '/static/js/family-tasks.js' in INDEX
    assert '/api/family/tasks' in TASKS_JS
    assert 'credentials: "same-origin"' in TASKS_JS
    assert "replaceChildren" in TASKS_JS
    for forbidden in ["innerHTML", "insertAdjacentHTML", "localStorage", "sessionStorage", "eval("]:
        assert forbidden not in TASKS_JS
    assert ".family-task-list" in TASKS_CSS
    assert 'body[data-family-role="wall_display"]' in TASKS_CSS


def test_family_task_router_is_registered_read_only():
    assert "from app.family_tasks import router as family_tasks_router" in MAIN_AUTH
    assert "app.include_router(family_tasks_router)" in MAIN_AUTH
    module = (ROOT / "app/family_tasks.py").read_text(encoding="utf-8")
    assert '@router.get("/api/family/tasks")' in module
    assert '@router.post("/api/family/tasks")' not in module


if __name__ == "__main__":
    for test in [
        test_default_task_entities_match_confirmed_home_assistant_entities,
        test_task_source_parser_accepts_only_plain_todo_entities,
        test_home_assistant_tasks_client_uses_get_items_response_and_needs_action_only,
        test_family_tasks_service_hides_private_lists_without_login,
        test_family_dashboard_replaces_task_placeholder_safely,
        test_family_task_router_is_registered_read_only,
    ]:
        test()
    print("Family tasks v0.12 tests OK")
