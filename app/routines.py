import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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


class ProgressPayload(BaseModel):
    expected_index: int | None = None


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


def _safe_state(raw, date_text):
    result = {"morning": _default_progress(date_text), "evening": _default_progress(date_text)}
    if not isinstance(raw, dict):
        return result
    for routine_id in ROUTINE_IDS:
        candidate = raw.get(routine_id)
        if not isinstance(candidate, dict) or candidate.get("date") != date_text:
            continue
        index = candidate.get("current_index")
        completed_ids = candidate.get("completed_task_ids")
        if not isinstance(index, int) or index < 0 or not isinstance(completed_ids, list):
            continue
        result[routine_id] = {
            "date": date_text,
            "current_index": index,
            "completed_task_ids": [item for item in completed_ids if isinstance(item, str)],
            "completed_at": candidate.get("completed_at") if isinstance(candidate.get("completed_at"), str) else None,
            "updated_at": candidate.get("updated_at") if isinstance(candidate.get("updated_at"), str) else None,
        }
    return result


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


class RoutineStore:
    def __init__(self, path=DEFAULT_STATE_PATH, now_provider=local_now, definitions=None):
        self.path = Path(path)
        self.now_provider = now_provider
        self.definitions = definitions or definition_store
        self._lock = threading.RLock()

    def _read_unlocked(self, date_text):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return _safe_state(None, date_text)
        return _safe_state(raw, date_text)

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

    def snapshot(self, now=None):
        current = local_now(now or self.now_provider())
        date_text = current.date().isoformat()
        with self._lock:
            state = self._read_unlocked(date_text)
            for routine_id in ROUTINE_IDS:
                _reconcile_progress(state[routine_id], self._tasks(routine_id, current.date()))
            self._write_unlocked(state)
            return self._response(state, current)

    def change(self, routine_id, action, expected_index=None, now=None):
        if routine_id not in ROUTINE_IDS:
            raise KeyError(routine_id)
        current = local_now(now or self.now_provider())
        date_text = current.date().isoformat()
        timestamp = current.isoformat(timespec="seconds")
        tasks = self._tasks(routine_id, current.date())
        with self._lock:
            state = self._read_unlocked(date_text)
            progress = _reconcile_progress(state[routine_id], tasks)
            index = progress["current_index"]
            if action == "complete":
                if expected_index is not None and expected_index != index:
                    return self._response(state, current)
                if index < len(tasks):
                    progress["completed_task_ids"].append(tasks[index].id)
                    progress["current_index"] = index + 1
                    progress["completed_at"] = timestamp if index + 1 >= len(tasks) else None
                    progress["updated_at"] = timestamp
            elif action == "back":
                if expected_index is not None and expected_index != index:
                    return self._response(state, current)
                if index > 0:
                    progress["completed_task_ids"] = progress["completed_task_ids"][:-1]
                    progress["current_index"] = index - 1
                    progress["completed_at"] = None
                    progress["updated_at"] = timestamp
            elif action == "reset":
                state[routine_id] = _default_progress(date_text)
                state[routine_id]["updated_at"] = timestamp
            else:
                raise ValueError(action)
            self._write_unlocked(state)
            return self._response(state, current)

    def reconcile_definition(self, routine_id, reset=False, now=None):
        current = local_now(now or self.now_provider())
        date_text = current.date().isoformat()
        with self._lock:
            state = self._read_unlocked(date_text)
            if reset:
                state[routine_id] = _default_progress(date_text)
            else:
                _reconcile_progress(state[routine_id], self._tasks(routine_id, current.date()))
            self._write_unlocked(state)
            return self._response(state, current)

    def _response(self, state, current):
        routines = {}
        definitions = self.definitions.all()
        for routine_id in ("morning", "evening"):
            tasks = tasks_for_date(definitions[routine_id], current.date())
            progress = _reconcile_progress(state[routine_id], tasks)
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


@router.get("/api/family/routines")
def family_routines(request: Request):
    if _current_user(request) is None:
        return {"status": "authentication_required", "routines": []}
    return routine_store.snapshot()


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
    if _current_user(request) is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    expected_index = payload.expected_index if payload is not None else None
    return routine_store.change(routine_id, action, expected_index)


@router.post("/api/family/routines/{routine_id}/complete")
def complete_routine(request: Request, routine_id: str, payload: ProgressPayload):
    return _change(request, routine_id, "complete", payload)


@router.post("/api/family/routines/{routine_id}/back")
def back_routine(request: Request, routine_id: str, payload: ProgressPayload):
    return _change(request, routine_id, "back", payload)


@router.post("/api/family/routines/{routine_id}/reset")
def reset_routine(request: Request, routine_id: str):
    return _change(request, routine_id, "reset")


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
    return {**_definitions_response(), "progress": routine_store.snapshot()["routines"]}


@router.post("/api/family/routines/definitions/{routine_id}/reset-default")
def reset_routine_definition(request: Request, routine_id: str):
    if routine_id not in ROUTINE_IDS:
        raise HTTPException(status_code=404, detail="Routine not found")
    if _editor_user(request) is None:
        raise HTTPException(status_code=403, detail="Adult role required")
    definition_store.reset_default(routine_id)
    routine_store.reconcile_definition(routine_id, reset=True)
    return {**_definitions_response(), "progress": routine_store.snapshot()["routines"]}
