import copy
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import config
from app.family_people import list_family_people
from app.family_task_assignments import FamilyTaskAssignmentStore
from app.family_visibility import role_can_do
from app.home_assistant import (
    HomeAssistantClient,
    HomeAssistantConfigurationError,
    HomeAssistantUnavailable,
    load_home_assistant_connection,
)

TODO_ENTITY_RE = re.compile(r"^todo\.[a-z0-9_]+$")
AUTHENTICATED_ROLES = {"owner", "adult", "child", "wall_display"}
EDITOR_ROLES = {"owner", "adult"}
MAX_LABEL_LENGTH = 32
MAX_SUMMARY_LENGTH = 160
MAX_DESCRIPTION_LENGTH = 320
MAX_ITEM_ID_LENGTH = 200


class FamilyTasksConfigurationError(ValueError):
    pass


class CompleteTaskRequest(BaseModel):
    item: str = Field(min_length=1, max_length=MAX_ITEM_ID_LENGTH)


class CreateTaskRequest(BaseModel):
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)


class UpdateTaskRequest(BaseModel):
    item: str = Field(min_length=1, max_length=MAX_ITEM_ID_LENGTH)
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)


class RemoveTaskRequest(BaseModel):
    item: str = Field(min_length=1, max_length=MAX_ITEM_ID_LENGTH)


@dataclass(frozen=True)
class TaskSource:
    entity_id: str = field(repr=False)
    key: str
    label: str


@dataclass(frozen=True)
class FamilyTasksSettings:
    connection: object = field(repr=False)
    sources: tuple[TaskSource, ...]
    cache_seconds: int
    stale_seconds: int
    max_items: int

    def signature(self):
        return (
            self.connection.base_url,
            tuple((source.entity_id, source.key, source.label) for source in self.sources),
            self.cache_seconds,
            self.stale_seconds,
            self.max_items,
        )


def _plain_label(value):
    label = " ".join(value.strip().split())
    if not label or len(label) > MAX_LABEL_LENGTH:
        raise FamilyTasksConfigurationError("Task list label is invalid")
    if any(not (character.isalnum() or character in " ._-'ÆØÅæøå") for character in label):
        raise FamilyTasksConfigurationError("Task list label is invalid")
    return label


def _source_key(entity_id):
    return entity_id.split(".", 1)[1].replace("_", "-")


def parse_task_sources(raw_value):
    sources = []
    seen = set()
    for raw_entry in raw_value.split(","):
        parts = [part.strip() for part in raw_entry.split("|")]
        if len(parts) != 2 or any(not part for part in parts):
            raise FamilyTasksConfigurationError("Task list mapping is invalid")
        entity_id, raw_label = parts
        if not TODO_ENTITY_RE.fullmatch(entity_id):
            raise FamilyTasksConfigurationError("Task list entity is invalid")
        if entity_id in seen:
            raise FamilyTasksConfigurationError("Task list entity is duplicated")
        seen.add(entity_id)
        sources.append(TaskSource(entity_id, _source_key(entity_id), _plain_label(raw_label)))
    if not sources:
        raise FamilyTasksConfigurationError("Task list mapping is empty")
    return tuple(sources)


def load_family_tasks_settings():
    try:
        values = config.family_tasks_configuration()
    except ValueError as exc:
        raise FamilyTasksConfigurationError("Task list configuration is invalid") from exc
    raw_sources = values["sources"]
    if not raw_sources:
        return None
    try:
        connection = load_home_assistant_connection()
    except HomeAssistantConfigurationError as exc:
        raise FamilyTasksConfigurationError("Task list configuration is invalid") from exc
    if connection is None:
        return None
    if values["stale_seconds"] < values["cache_seconds"]:
        raise FamilyTasksConfigurationError("FAMILY_TASKS_STALE_SECONDS must be at least FAMILY_TASKS_CACHE_SECONDS")
    return FamilyTasksSettings(
        connection=connection,
        sources=parse_task_sources(raw_sources),
        cache_seconds=values["cache_seconds"],
        stale_seconds=values["stale_seconds"],
        max_items=values["max_items"],
    )


def _clean_text(value, maximum):
    return " ".join(str(value or "").split())[:maximum]


def _required_text(value, maximum, message):
    cleaned = _clean_text(value, maximum)
    if not cleaned:
        raise ValueError(message)
    return cleaned


def _optional_text(value, maximum):
    return _clean_text(value, maximum) or None


def _normalize_item(raw_item, source):
    if not isinstance(raw_item, dict):
        return None
    uid = _clean_text(raw_item.get("uid"), MAX_ITEM_ID_LENGTH)
    summary = _clean_text(raw_item.get("summary"), MAX_SUMMARY_LENGTH)
    if not uid or not summary or raw_item.get("status") != "needs_action":
        return None
    due = _clean_text(raw_item.get("due"), 40) or None
    return {
        "list": {"key": source.key, "label": source.label},
        "uid": uid,
        "summary": summary,
        "due": due,
        "description": _clean_text(raw_item.get("description"), MAX_DESCRIPTION_LENGTH) or None,
    }


def _due_sort_value(item):
    due = item.get("due")
    if not due:
        return (1, "", item["summary"].casefold())
    try:
        normalized = datetime.fromisoformat(due.replace("Z", "+00:00")).isoformat()
    except ValueError:
        normalized = due
    return (0, normalized, item["summary"].casefold())


class HomeAssistantTasksClient:
    def __init__(self, settings, client_factory: Callable = httpx.Client):
        self.settings = settings
        self.client_factory = client_factory

    def fetch(self):
        client = HomeAssistantClient(self.settings.connection, self.client_factory)
        lists = []
        failures = 0
        for source in self.settings.sources:
            try:
                payload = client.post_json(
                    "/api/services/todo/get_items",
                    params={"return_response": ""},
                    json_body={"entity_id": source.entity_id, "status": "needs_action"},
                )
                response = payload.get("service_response", {}) if isinstance(payload, dict) else {}
                source_data = response.get(source.entity_id, {}) if isinstance(response, dict) else {}
                raw_items = source_data.get("items") if isinstance(source_data, dict) else None
                if not isinstance(raw_items, list):
                    raise HomeAssistantUnavailable("Home Assistant task response is invalid")
                items = []
                for raw_item in raw_items:
                    item = _normalize_item(raw_item, source)
                    if item is not None:
                        items.append(item)
                items.sort(key=_due_sort_value)
                lists.append({"key": source.key, "label": source.label, "items": items})
            except HomeAssistantUnavailable:
                failures += 1
        remaining = self.settings.max_items
        limited_lists = []
        for task_list in lists:
            items = task_list["items"][:remaining]
            remaining = max(0, remaining - len(items))
            limited_lists.append({**task_list, "items": items})
        return limited_lists, failures

    def complete(self, source, item_uid):
        self._call(
            "/api/services/todo/update_item",
            {"entity_id": source.entity_id, "item": item_uid, "status": "completed"},
        )

    def add(self, source, summary, description=None):
        payload = {"entity_id": source.entity_id, "item": summary}
        if description:
            payload["description"] = description
        self._call("/api/services/todo/add_item", payload)

    def update(self, source, item_uid, summary, description=None):
        payload = {
            "entity_id": source.entity_id,
            "item": item_uid,
            "rename": summary,
            "description": description or "",
        }
        self._call("/api/services/todo/update_item", payload)

    def remove(self, source, item_uid):
        self._call(
            "/api/services/todo/remove_item",
            {"entity_id": source.entity_id, "item": item_uid},
        )

    def _call(self, path, payload):
        HomeAssistantClient(self.settings.connection, self.client_factory).post_json(
            path,
            json_body=payload,
        )


def _empty_snapshot(status, sources=(), unavailable_lists=0):
    return {
        "status": status,
        "lists": [{"key": source.key, "label": source.label, "items": []} for source in sources],
        "total": 0,
        "unavailable_lists": unavailable_lists,
        "stale": False,
    }


def _snapshot(status, lists, failures):
    return {
        "status": status,
        "lists": copy.deepcopy(lists),
        "total": sum(len(task_list["items"]) for task_list in lists),
        "unavailable_lists": failures,
        "stale": False,
    }


def _task_permissions(current_user):
    role = current_user.get("role") if isinstance(current_user, dict) else None
    return {
        "can_add": role_can_do(role, "task_add"),
        "can_complete": role_can_do(role, "task_complete"),
        "can_edit": role_can_do(role, "task_edit"),
        "can_remove": role_can_do(role, "task_remove"),
    }


def _public_snapshot(snapshot, current_user):
    authenticated = isinstance(current_user, dict) and current_user.get("role") in AUTHENTICATED_ROLES
    if authenticated:
        result = copy.deepcopy(snapshot)
        result.update(_task_permissions(current_user))
        return result
    return {
        "status": "authentication_required",
        "lists": [],
        "people": [],
        "total": 0,
        "unavailable_lists": 0,
        "stale": False,
        "can_add": False,
        "can_complete": False,
        "can_edit": False,
        "can_remove": False,
    }


def _authenticated(current_user):
    return isinstance(current_user, dict) and current_user.get("role") in AUTHENTICATED_ROLES


def _can_perform(current_user, action):
    role = current_user.get("role") if isinstance(current_user, dict) else None
    return _authenticated(current_user) and role_can_do(role, action)


class FamilyTasksService:
    def __init__(
        self,
        settings_loader=load_family_tasks_settings,
        client_factory=httpx.Client,
        monotonic=time.monotonic,
        assignment_store=None,
        people_loader=list_family_people,
    ):
        self.settings_loader = settings_loader
        self.client_factory = client_factory
        self.monotonic = monotonic
        self.assignment_store = assignment_store or FamilyTaskAssignmentStore()
        self.people_loader = people_loader
        self._lock = threading.Lock()
        self._cached = None
        self._cached_at = None
        self._signature = None

    def clear_cache(self):
        with self._lock:
            self._cached = None
            self._cached_at = None
            self._signature = None

    def _decorate_assignments(self, snapshot):
        result = copy.deepcopy(snapshot)
        people = self.people_loader()
        person_ids = {
            person["user_id"]
            for person in people
            if person.get("user_id")
        }

        task_keys = []
        for task_list in result.get("lists", []):
            list_key = task_list.get("key")
            for item in task_list.get("items", []):
                task_keys.append((list_key, item.get("uid")))

        assignments = self.assignment_store.get_many(task_keys)
        counts = {None: 0}
        counts.update({person_id: 0 for person_id in person_ids})

        for task_list in result.get("lists", []):
            list_key = task_list.get("key")
            for item in task_list.get("items", []):
                task_key = (list_key, item.get("uid"))
                assignee_id = assignments.get(task_key)
                if assignee_id not in person_ids:
                    assignee_id = None
                item["assignee_id"] = assignee_id
                counts[assignee_id] = counts.get(assignee_id, 0) + 1

        result["people"] = [
            {
                "user_id": None,
                "display_name": "Familien",
                "role": "family",
                "count": counts.get(None, 0),
            },
            *[
                {
                    **person,
                    "count": counts.get(person["user_id"], 0),
                }
                for person in people
            ],
        ]
        return result

    def _public_tasks(self, snapshot, current_user):
        return _public_snapshot(
            self._decorate_assignments(snapshot),
            current_user,
        )

    def get_tasks(self, current_user=None):
        try:
            settings = self.settings_loader()
        except FamilyTasksConfigurationError:
            return self._public_tasks(_empty_snapshot("unavailable"), current_user)
        if settings is None:
            return self._public_tasks(_empty_snapshot("not_configured"), current_user)

        signature = settings.signature()
        now = self.monotonic()
        with self._lock:
            if self._signature != signature:
                self._cached = None
                self._cached_at = None
                self._signature = signature
            if self._cached is not None and self._cached_at is not None:
                age = max(0.0, now - self._cached_at)
                if age < settings.cache_seconds:
                    return self._public_tasks(self._cached, current_user)

            lists, failures = HomeAssistantTasksClient(settings, self.client_factory).fetch()
            if failures < len(settings.sources):
                status = "partial" if failures else "ok"
                snapshot = _snapshot(status, lists, failures)
                self._cached = copy.deepcopy(snapshot)
                self._cached_at = now
                return self._public_tasks(snapshot, current_user)

            if self._cached is not None and self._cached_at is not None:
                age = max(0.0, now - self._cached_at)
                if age < settings.stale_seconds:
                    stale = copy.deepcopy(self._cached)
                    stale["status"] = "stale"
                    stale["stale"] = True
                    stale["unavailable_lists"] = len(settings.sources)
                    return self._public_tasks(stale, current_user)

            return self._public_tasks(
                _empty_snapshot("unavailable", settings.sources, len(settings.sources)),
                current_user,
            )

    def _settings_and_source(self, list_key):
        settings = self.settings_loader()
        if settings is None:
            raise FamilyTasksConfigurationError("Task lists are not configured")
        source = next((candidate for candidate in settings.sources if candidate.key == list_key), None)
        if source is None:
            raise KeyError("Task list was not found")
        return settings, source

    def complete_task(self, list_key, item_uid, current_user=None):
        if not _can_perform(current_user, "task_complete"):
            raise PermissionError("Task completion is not allowed")
        settings, source = self._settings_and_source(list_key)
        cleaned_uid = _required_text(item_uid, MAX_ITEM_ID_LENGTH, "Task item is invalid")
        HomeAssistantTasksClient(settings, self.client_factory).complete(source, cleaned_uid)
        self.clear_cache()
        return self.get_tasks(current_user)

    def add_task(self, list_key, summary, description, current_user=None):
        if not _can_perform(current_user, "task_add"):
            raise PermissionError("Task creation is not allowed")
        settings, source = self._settings_and_source(list_key)
        cleaned_summary = _required_text(summary, MAX_SUMMARY_LENGTH, "Task summary is invalid")
        cleaned_description = _optional_text(description, MAX_DESCRIPTION_LENGTH)
        HomeAssistantTasksClient(settings, self.client_factory).add(
            source,
            cleaned_summary,
            cleaned_description,
        )
        self.clear_cache()
        return self.get_tasks(current_user)

    def update_task(self, list_key, item_uid, summary, description, current_user=None):
        if not _can_perform(current_user, "task_edit"):
            raise PermissionError("Task editing is not allowed")
        settings, source = self._settings_and_source(list_key)
        cleaned_uid = _required_text(item_uid, MAX_ITEM_ID_LENGTH, "Task item is invalid")
        cleaned_summary = _required_text(summary, MAX_SUMMARY_LENGTH, "Task summary is invalid")
        cleaned_description = _optional_text(description, MAX_DESCRIPTION_LENGTH)
        HomeAssistantTasksClient(settings, self.client_factory).update(
            source,
            cleaned_uid,
            cleaned_summary,
            cleaned_description,
        )
        self.clear_cache()
        return self.get_tasks(current_user)

    def remove_task(self, list_key, item_uid, current_user=None):
        if not _can_perform(current_user, "task_remove"):
            raise PermissionError("Task removal is not allowed")
        settings, source = self._settings_and_source(list_key)
        cleaned_uid = _required_text(item_uid, MAX_ITEM_ID_LENGTH, "Task item is invalid")
        HomeAssistantTasksClient(settings, self.client_factory).remove(source, cleaned_uid)
        self.clear_cache()
        return self.get_tasks(current_user)


family_tasks_service = FamilyTasksService()
router = APIRouter()


def _handle_task_error(exc):
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail="Task list not found") from exc
    if isinstance(exc, FamilyTasksConfigurationError):
        raise HTTPException(status_code=503, detail="Tasks are unavailable") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail="Task data is invalid") from exc
    if isinstance(exc, HomeAssistantUnavailable):
        raise HTTPException(status_code=503, detail="Tasks are unavailable") from exc
    raise exc


@router.get("/api/family/tasks")
def family_tasks(request: Request):
    current_user = getattr(request.state, "current_user", None)
    return family_tasks_service.get_tasks(current_user)


@router.post("/api/family/tasks/{list_key}/complete")
def complete_family_task(list_key: str, payload: CompleteTaskRequest, request: Request):
    current_user = getattr(request.state, "current_user", None)
    try:
        return family_tasks_service.complete_task(list_key, payload.item, current_user)
    except Exception as exc:
        _handle_task_error(exc)


@router.post("/api/family/tasks/{list_key}/items")
def add_family_task(list_key: str, payload: CreateTaskRequest, request: Request):
    current_user = getattr(request.state, "current_user", None)
    try:
        return family_tasks_service.add_task(
            list_key,
            payload.summary,
            payload.description,
            current_user,
        )
    except Exception as exc:
        _handle_task_error(exc)


@router.put("/api/family/tasks/{list_key}/items")
def update_family_task(list_key: str, payload: UpdateTaskRequest, request: Request):
    current_user = getattr(request.state, "current_user", None)
    try:
        return family_tasks_service.update_task(
            list_key,
            payload.item,
            payload.summary,
            payload.description,
            current_user,
        )
    except Exception as exc:
        _handle_task_error(exc)


@router.delete("/api/family/tasks/{list_key}/items")
def remove_family_task(list_key: str, payload: RemoveTaskRequest, request: Request):
    current_user = getattr(request.state, "current_user", None)
    try:
        return family_tasks_service.remove_task(list_key, payload.item, current_user)
    except Exception as exc:
        _handle_task_error(exc)
