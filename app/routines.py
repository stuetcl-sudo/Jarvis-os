import json
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import config

ROUTINE_IDS = {"morning", "evening"}
ROUTINE_ROLES = {"owner", "adult", "child", "wall_display"}
DEFAULT_STATE_PATH = Path("/data/family_routines.json")


@dataclass(frozen=True)
class RoutineTask:
    id: str
    title: str
    pictogram: str
    time: str | None = None


MORNING_TASKS = (
    RoutineTask("morning_wake", "Vågne op", "wake", "06:00"),
    RoutineTask("morning_tv", "Se lidt TV", "tv"),
    RoutineTask("morning_breakfast", "Spise morgenmad", "breakfast"),
    RoutineTask("morning_clothes", "Tage tøj på", "clothes"),
    RoutineTask("morning_teeth", "Børste tænder", "teeth"),
    RoutineTask("morning_ipad", "Spille lidt på iPad", "tablet"),
    RoutineTask("morning_outerwear", "Tage overtøj på", "outerwear"),
    RoutineTask("morning_school", "Gå i skole", "school"),
)

EVENING_BASE_TASKS = (
    RoutineTask("evening_homework", "Lektier", "homework", "16:00"),
    RoutineTask("evening_exercise", "Øvelser og træning", "exercise", "16:30"),
    RoutineTask("evening_play_before", "Fri leg", "play"),
    RoutineTask("evening_dinner", "Spise aftensmad", "dinner", "18:00"),
    RoutineTask("evening_cleanup", "Rydde af bordet", "cleanup"),
    RoutineTask("evening_play_after", "Fri leg", "play"),
    RoutineTask("evening_teeth", "Børste tænder", "teeth", "20:00"),
    RoutineTask("evening_undress", "Tage tøj af", "clothes"),
    RoutineTask("evening_laundry", "Lægge beskidt tøj i vasketøjskurven", "laundry"),
    RoutineTask("evening_bed", "Gå i seng", "bed"),
    RoutineTask("evening_audio", "Høre musik eller lydbog", "audio"),
    RoutineTask("evening_sleep", "Sove", "sleep", "20:30"),
)
BATH_TASK = RoutineTask("evening_bath", "Gå i bad", "bath")


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
    if routine_id == "morning":
        return MORNING_TASKS
    if routine_id != "evening":
        raise KeyError(routine_id)
    tasks = list(EVENING_BASE_TASKS)
    if local_date.weekday() in {2, 6}:
        cleanup_index = next(index for index, task in enumerate(tasks) if task.id == "evening_cleanup")
        tasks.insert(cleanup_index + 1, BATH_TASK)
    return tuple(tasks)


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


class RoutineStore:
    def __init__(self, path=DEFAULT_STATE_PATH, now_provider=local_now):
        self.path = Path(path)
        self.now_provider = now_provider
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

    def snapshot(self, now=None):
        current = local_now(now or self.now_provider())
        date_text = current.date().isoformat()
        with self._lock:
            state = self._read_unlocked(date_text)
            self._write_unlocked(state)
            return self._response(state, current)

    def change(self, routine_id, action, expected_index=None, now=None):
        if routine_id not in ROUTINE_IDS:
            raise KeyError(routine_id)
        current = local_now(now or self.now_provider())
        date_text = current.date().isoformat()
        timestamp = current.isoformat(timespec="seconds")
        tasks = routine_tasks(routine_id, current.date())
        with self._lock:
            state = self._read_unlocked(date_text)
            progress = state[routine_id]
            index = min(progress["current_index"], len(tasks))
            if action == "complete":
                if expected_index is not None and expected_index != index:
                    return self._response(state, current)
                if index < len(tasks):
                    completed_ids = list(progress["completed_task_ids"])
                    task_id = tasks[index].id
                    if task_id not in completed_ids:
                        completed_ids.append(task_id)
                    index += 1
                    progress["completed_task_ids"] = completed_ids
                    progress["current_index"] = index
                    progress["completed_at"] = timestamp if index >= len(tasks) else None
                    progress["updated_at"] = timestamp
            elif action == "back":
                if expected_index is not None and expected_index != index:
                    return self._response(state, current)
                if index > 0:
                    index -= 1
                    progress["current_index"] = index
                    progress["completed_task_ids"] = [task.id for task in tasks[:index]]
                    progress["completed_at"] = None
                    progress["updated_at"] = timestamp
            elif action == "reset":
                state[routine_id] = _default_progress(date_text)
                state[routine_id]["updated_at"] = timestamp
            else:
                raise ValueError(action)
            self._write_unlocked(state)
            return self._response(state, current)

    def _response(self, state, current):
        routines = {}
        labels = {"morning": "Godmorgen-rutine", "evening": "Aftenrutine"}
        for routine_id in ("morning", "evening"):
            tasks = routine_tasks(routine_id, current.date())
            progress = state[routine_id]
            index = min(progress["current_index"], len(tasks))
            completed = index >= len(tasks)
            current_task = None if completed else tasks[index]
            routines[routine_id] = {
                "label": labels[routine_id],
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
        return {
            "status": "ok",
            "recommended": "morning" if current.hour < 12 else "evening",
            "routines": routines,
        }


routine_store = RoutineStore()
router = APIRouter()


def _current_user(request):
    user = getattr(request.state, "current_user", None)
    return user if isinstance(user, dict) and user.get("role") in ROUTINE_ROLES else None


@router.get("/api/family/routines")
def family_routines(request: Request):
    if _current_user(request) is None:
        return {"status": "authentication_required", "routines": []}
    return routine_store.snapshot()


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
