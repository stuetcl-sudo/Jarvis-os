import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.family_people import list_family_people
from app.routine_definitions import (
    DEFAULT_DEFINITIONS,
    EDITOR_ROLES,
    PICTOGRAM_LABELS,
    ROUTINE_IDS,
    WEEKDAY_LABELS,
    DefinitionValidationError,
    RoutineDefinitionStore,
    RoutineTask,
    definition_to_dict,
    tasks_for_date,
)

ROUTINE_ROLES = {"owner", "adult", "child", "wall_display"}
DEFAULT_STATE_PATH = Path("/data/family_routines.json")
MORNING_TASKS = DEFAULT_DEFINITIONS["morning"].tasks
EVENING_BASE_TASKS = tuple(task for task in DEFAULT_DEFINITIONS["evening"].tasks if task.id != "evening_bath")
BATH_TASK = next(task for task in DEFAULT_DEFINITIONS["evening"].tasks if task.id == "evening_bath")
STATE_VERSION = 2


class ProgressPayload(BaseModel):
    expected_index: int | None = None
    person_id: str | None = None


def routine_timezone():
    name = os.getenv("ROUTINE_TIMEZONE", "Europe/Copenhagen").strip() or "Europe/Copenhagen"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Copenhagen")


def local_now(now=None):
    tz = routine_timezone()
    current = now or datetime.now(tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    return current.astimezone(tz)


def routine_tasks(routine_id, local_date):
    return tasks_for_date(definition_store.get(routine_id), local_date)


def _default_progress(date_text):
    return {
        "date": date_text,
        "current_index": 0,
        "completed_task_ids": [],
        "completed_at": None,
        "updated_at": None,
    }


def _default_person_state(date_text):
    return {"morning": _default_progress(date_text), "evening": _default_progress(date_text)}


def _safe_progress(candidate, date_text):
    result = _default_progress(date_text)
    if not isinstance(candidate, dict) or candidate.get("date") != date_text:
        return result
    index = candidate.get("current_index")
    completed_ids = candidate.get("completed_task_ids")
    if not isinstance(index, int) or isinstance(index, bool) or index < 0 or not isinstance(completed_ids, list):
        return result
    return {
        "date": date_text,
        "current_index": index,
        "completed_task_ids": [item for item in completed_ids if isinstance(item, str)],
        "completed_at": candidate.get("completed_at") if isinstance(candidate.get("completed_at"), str) else None,
        "updated_at": candidate.get("updated_at") if isinstance(candidate.get("updated_at"), str) else None,
    }


def _safe_legacy_state(raw, date_text):
    result = _default_person_state(date_text)
    if not isinstance(raw, dict):
        return result
    for routine_id in ROUTINE_IDS:
        result[routine_id] = _safe_progress(raw.get(routine_id), date_text)
    return result


def _safe_versioned_state(raw, date_text, migration_person_id=None):
    state = {"version": STATE_VERSION, "date": date_text, "persons": {}}
    if isinstance(raw, dict) and raw.get("version") == STATE_VERSION and raw.get("date") == date_text:
        raw_persons = raw.get("persons")
        if isinstance(raw_persons, dict):
            for raw_person_id, raw_progress in raw_persons.items():
                person_id = str(raw_person_id or "").strip()
                if not person_id or not isinstance(raw_progress, dict):
                    continue
                state["persons"][person_id] = {
                    routine_id: _safe_progress(raw_progress.get(routine_id), date_text)
                    for routine_id in ("morning", "evening")
                }
        return state
    if migration_person_id and isinstance(raw, dict) and any(key in raw for key in ROUTINE_IDS):
        state["persons"][migration_person_id] = _safe_legacy_state(raw, date_text)
    return state


def _reconcile_progress(progress, tasks):
    valid_ids = {task.id for task in tasks}
    remaining = [task_id for task_id in progress["completed_task_ids"] if task_id in valid_ids]
    prefix = []
    for task in tasks:
        if remaining and task.id == remaining[0]:
            prefix.append(remaining.pop(0))
        else:
            break
    progress["completed_task_ids"] = prefix
    progress["current_index"] = len(prefix)
    if len(prefix) < len(tasks):
        progress["completed_at"] = None
    return progress


def _clean_person_id(person_id):
    if person_id is None:
        return None
    cleaned = str(person_id).strip()
    if not cleaned or len(cleaned) > 128 or any(ord(character) < 33 for character in cleaned):
        raise ValueError("person_id is invalid")
    return cleaned


class RoutineStore:
    def __init__(self, path=DEFAULT_STATE_PATH, now_provider=local_now, definitions=None):
        self.path = Path(path)
        self.now_provider = now_provider
        self.definitions = definitions or definition_store
        self._lock = threading.RLock()

    def _load_raw_unlocked(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return None

    def _read_unlocked(self, date_text, person_id=None):
        raw = self._load_raw_unlocked()
        if person_id is None:
            return _safe_legacy_state(raw, date_text)
        return _safe_versioned_state(raw, date_text, migration_person_id=person_id)

    def _write_unlocked(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix="family_routines_", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self.path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def _tasks(self, routine_id, local_date):
        return tasks_for_date(self.definitions.get(routine_id), local_date)

    def snapshot(self, now=None, person_id=None):
        person_id = _clean_person_id(person_id)
        current = local_now(now or self.now_provider())
        date_text = current.date().isoformat()
        with self._lock:
            state = self._read_unlocked(date_text, person_id)
            if person_id is None:
                progress_state = state
            else:
                progress_state = state["persons"].setdefault(person_id, _default_person_state(date_text))
            for routine_id in ROUTINE_IDS:
                _reconcile_progress(progress_state[routine_id], self._tasks(routine_id, current.date()))
            self._write_unlocked(state)
            return self._response(progress_state, current)

    def change(self, routine_id, action, expected_index=None, now=None, person_id=None):
        if routine_id not in ROUTINE_IDS:
            raise KeyError(routine_id)
        person_id = _clean_person_id(person_id)
        current = local_now(now or self.now_provider())
        date_text = current.date().isoformat()
        timestamp = current.isoformat(timespec="seconds")
        tasks = self._tasks(routine_id, current.date())
        with self._lock:
            state = self._read_unlocked(date_text, person_id)
            if person_id is None:
                progress_state = state
            else:
                progress_state = state["persons"].setdefault(person_id, _default_person_state(date_text))
            progress = _reconcile_progress(progress_state[routine_id], tasks)
            index = progress["current_index"]
            if action == "complete":
                if expected_index is not None and expected_index != index:
                    return self._response(progress_state, current)
                if index < len(tasks):
                    progress["completed_task_ids"].append(tasks[index].id)
                    progress["current_index"] = index + 1
                    progress["completed_at"] = timestamp if index + 1 >= len(tasks) else None
                    progress["updated_at"] = timestamp
            elif action == "back":
                if expected_index is not None and expected_index != index:
                    return self._response(progress_state, current)
                if index > 0:
                    progress["completed_task_ids"] = progress["completed_task_ids"][:-1]
                    progress["current_index"] = index - 1
                    progress["completed_at"] = None
                    progress["updated_at"] = timestamp
            elif action == "reset":
                progress_state[routine_id] = _default_progress(date_text)
                progress_state[routine_id]["updated_at"] = timestamp
            else:
                raise ValueError(action)
            self._write_unlocked(state)
            return self._response(progress_state, current)

    def reconcile_definition(self, routine_id, reset=False, now=None):
        if routine_id not in ROUTINE_IDS:
            raise KeyError(routine_id)
        current = local_now(now or self.now_provider())
        date_text = current.date().isoformat()
        with self._lock:
            raw = self._load_raw_unlocked()
            if isinstance(raw, dict) and raw.get("version") == STATE_VERSION:
                state = _safe_versioned_state(raw, date_text)
                for progress_state in state["persons"].values():
                    if reset:
                        progress_state[routine_id] = _default_progress(date_text)
                    else:
                        _reconcile_progress(progress_state[routine_id], self._tasks(routine_id, current.date()))
                self._write_unlocked(state)
                return None
            state = _safe_legacy_state(raw, date_text)
            if reset:
                state[routine_id] = _default_progress(date_text)
            else:
                _reconcile_progress(state[routine_id], self._tasks(routine_id, current.date()))
            self._write_unlocked(state)
            return self._response(state, current)

    def _response(self, progress_state, current):
        routines = {}
        definitions = self.definitions.all()
        for routine_id in ("morning", "evening"):
            tasks = tasks_for_date(definitions[routine_id], current.date())
            progress = _reconcile_progress(progress_state[routine_id], tasks)
            index = progress["current_index"]
            completed = index >= len(tasks)
            current_task = None if completed else tasks[index]
            routines[routine_id] = {
                "label": definitions[routine_id].label,
                "date": current.date().isoformat(),
                "current_index": index,
                "total": len(tasks),
                "completed": completed,
                "current_task": None if current_task is None else {
                    "id": current_task.id,
                    "title": current_task.title,
                    "pictogram": current_task.pictogram,
                    "time": current_task.time,
                },
            }
        return {"status": "ok", "recommended": "morning" if current.hour < 12 else "evening", "routines": routines}


definition_store = RoutineDefinitionStore()
routine_store = RoutineStore(definitions=definition_store)
router = APIRouter()


def _current_user(request):
    user = getattr(request.state, "current_user", None)
    return user if isinstance(user, dict) and user.get("role") in ROUTINE_ROLES else None


def _editor_user(request):
    user = _current_user(request)
    return user if user and user.get("role") in EDITOR_ROLES else None


def _definitions_response():
    definitions = definition_store.all()
    return {
        "status": "ok",
        "routines": {routine_id: definition_to_dict(definitions[routine_id]) for routine_id in ("morning", "evening")},
        "pictograms": [{"key": key, "label": label} for key, label in PICTOGRAM_LABELS.items()],
        "weekdays": [{"key": key, "label": label} for key, label in WEEKDAY_LABELS],
    }


def _select_person(current_user, requested_person_id=None):
    people = list_family_people()
    if not people:
        return people, None
    by_id = {person["user_id"]: person for person in people}
    if requested_person_id is not None:
        selected = str(requested_person_id).strip()
        if selected not in by_id:
            raise HTTPException(status_code=404, detail="Person not found")
        return people, selected
    own_id = str(current_user.get("user_id") or "").strip() if isinstance(current_user, dict) else ""
    if own_id in by_id:
        return people, own_id
    return people, people[0]["user_id"]


def _person_response(response, people, selected_person_id):
    return {
        **response,
        "persons": people,
        "selected_person_id": selected_person_id,
    }


@router.get("/api/family/routines")
def family_routines(request: Request, person_id: str | None = None):
    current_user = _current_user(request)
    if current_user is None:
        return {"status": "authentication_required", "routines": []}
    people, selected_person_id = _select_person(current_user, person_id)
    if selected_person_id is None:
        return {
            "status": "not_configured",
            "persons": [],
            "selected_person_id": None,
            "recommended": "morning",
            "routines": {},
        }
    return _person_response(routine_store.snapshot(person_id=selected_person_id), people, selected_person_id)


@router.get("/api/family/routines/definitions")
def routine_definitions(request: Request):
    if _current_user(request) is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if _editor_user(request) is None:
        raise HTTPException(status_code=403, detail="Adult role required")
    return _definitions_response()


def _change(request, routine_id, action, payload=None):
    if routine_id not in ROUTINE_IDS:
        raise HTTPException(status_code=404, detail="Routine not found")
    current_user = _current_user(request)
    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    requested_person_id = payload.person_id if payload is not None else None
    people, selected_person_id = _select_person(current_user, requested_person_id)
    if selected_person_id is None:
        raise HTTPException(status_code=409, detail="No family persons configured")
    expected_index = payload.expected_index if payload is not None else None
    response = routine_store.change(
        routine_id,
        action,
        expected_index,
        person_id=selected_person_id,
    )
    return _person_response(response, people, selected_person_id)


@router.post("/api/family/routines/{routine_id}/complete")
def complete_routine(request: Request, routine_id: str, payload: ProgressPayload):
    return _change(request, routine_id, "complete", payload)


@router.post("/api/family/routines/{routine_id}/back")
def back_routine(request: Request, routine_id: str, payload: ProgressPayload):
    return _change(request, routine_id, "back", payload)


@router.post("/api/family/routines/{routine_id}/reset")
def reset_routine(request: Request, routine_id: str, payload: ProgressPayload | None = None):
    return _change(request, routine_id, "reset", payload)


@router.put("/api/family/routines/definitions/{routine_id}")
def update_routine_definition(request: Request, routine_id: str, payload: dict):
    if routine_id not in ROUTINE_IDS:
        raise HTTPException(status_code=404, detail="Routine not found")
    if _editor_user(request) is None:
        raise HTTPException(status_code=403, detail="Adult role required")
    try:
        definition_store.update(routine_id, payload)
    except DefinitionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    routine_store.reconcile_definition(routine_id)
    current_user = _current_user(request)
    people, selected_person_id = _select_person(current_user)
    progress = routine_store.snapshot(person_id=selected_person_id)["routines"] if selected_person_id else {}
    return {**_definitions_response(), "progress": progress}


@router.post("/api/family/routines/definitions/{routine_id}/reset-default")
def reset_routine_definition(request: Request, routine_id: str):
    if routine_id not in ROUTINE_IDS:
        raise HTTPException(status_code=404, detail="Routine not found")
    if _editor_user(request) is None:
        raise HTTPException(status_code=403, detail="Adult role required")
    definition_store.reset_default(routine_id)
    routine_store.reconcile_definition(routine_id, reset=True)
    current_user = _current_user(request)
    people, selected_person_id = _select_person(current_user)
    progress = routine_store.snapshot(person_id=selected_person_id)["routines"] if selected_person_id else {}
    return {**_definitions_response(), "progress": progress}
