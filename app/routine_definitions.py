import copy
import json
import os
import re
import secrets
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

ROUTINE_IDS = {"morning", "evening"}
EDITOR_ROLES = {"owner", "adult"}
DEFAULT_DEFINITIONS_PATH = Path("/data/family_routine_definitions.json")
MAX_TASKS = 30
MAX_TITLE_LENGTH = 80
MAX_LABEL_LENGTH = 40
TASK_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
UNSAFE_TEXT_RE = re.compile(r"[<>]|https?://|www\.|javascript:|data:", re.IGNORECASE)
PICTOGRAM_LABELS = {
    "wake": "Vågne op",
    "tv": "Fjernsyn",
    "breakfast": "Morgenmad",
    "clothes": "Tøj",
    "teeth": "Tandbørste",
    "tablet": "Tablet",
    "outerwear": "Overtøj",
    "school": "Skole",
    "homework": "Lektier",
    "exercise": "Træning",
    "play": "Leg",
    "dinner": "Mad",
    "cleanup": "Rydde op",
    "bath": "Bad",
    "laundry": "Vasketøj",
    "bed": "Seng",
    "audio": "Musik eller lydbog",
    "sleep": "Sove",
    "complete": "Færdig",
}
WEEKDAY_LABELS = (
    (0, "Mandag"),
    (1, "Tirsdag"),
    (2, "Onsdag"),
    (3, "Torsdag"),
    (4, "Fredag"),
    (5, "Lørdag"),
    (6, "Søndag"),
)


class DefinitionValidationError(ValueError):
    pass


@dataclass(frozen=True)
class RoutineTask:
    id: str
    title: str
    pictogram: str
    time: str | None = None
    weekdays: tuple[int, ...] = ()


@dataclass(frozen=True)
class RoutineDefinition:
    id: str
    label: str
    tasks: tuple[RoutineTask, ...]


def _task(task_id, title, pictogram, time=None, weekdays=()):
    return RoutineTask(task_id, title, pictogram, time, tuple(weekdays))


DEFAULT_DEFINITIONS = {
    "morning": RoutineDefinition(
        "morning",
        "Godmorgen-rutine",
        (
            _task("morning_wake", "Vågne op", "wake", "06:00"),
            _task("morning_tv", "Se lidt TV", "tv"),
            _task("morning_breakfast", "Spise morgenmad", "breakfast"),
            _task("morning_clothes", "Tage tøj på", "clothes"),
            _task("morning_teeth", "Børste tænder", "teeth"),
            _task("morning_ipad", "Spille lidt på iPad", "tablet"),
            _task("morning_outerwear", "Tage overtøj på", "outerwear"),
            _task("morning_school", "Gå i skole", "school"),
        ),
    ),
    "evening": RoutineDefinition(
        "evening",
        "Aftenrutine",
        (
            _task("evening_homework", "Lektier", "homework", "16:00"),
            _task("evening_exercise", "Øvelser og træning", "exercise", "16:30"),
            _task("evening_play_before", "Fri leg", "play"),
            _task("evening_dinner", "Spise aftensmad", "dinner", "18:00"),
            _task("evening_cleanup", "Rydde af bordet", "cleanup"),
            _task("evening_bath", "Gå i bad", "bath", weekdays=(2, 6)),
            _task("evening_play_after", "Fri leg", "play"),
            _task("evening_teeth", "Børste tænder", "teeth", "20:00"),
            _task("evening_undress", "Tage tøj af", "clothes"),
            _task("evening_laundry", "Lægge beskidt tøj i vasketøjskurven", "laundry"),
            _task("evening_bed", "Gå i seng", "bed"),
            _task("evening_audio", "Høre musik eller lydbog", "audio"),
            _task("evening_sleep", "Sove", "sleep", "20:30"),
        ),
    ),
}


def _safe_text(value, field, maximum):
    if not isinstance(value, str):
        raise DefinitionValidationError(f"{field} skal være tekst")
    normalized = " ".join(value.strip().split())
    if not normalized or len(normalized) > maximum or UNSAFE_TEXT_RE.search(normalized):
        raise DefinitionValidationError(f"{field} er ugyldig")
    if any(ord(character) < 32 for character in normalized):
        raise DefinitionValidationError(f"{field} er ugyldig")
    return normalized


def _task_id(value, routine_id):
    if value in (None, ""):
        return f"{routine_id}_custom_{secrets.token_hex(6)}"
    if not isinstance(value, str) or not TASK_ID_RE.fullmatch(value):
        raise DefinitionValidationError("Trin-ID er ugyldigt")
    return value


def validate_definition(routine_id, payload, require_ids=False):
    if routine_id not in ROUTINE_IDS:
        raise KeyError(routine_id)
    if not isinstance(payload, dict) or set(payload) != {"label", "tasks"}:
        raise DefinitionValidationError("Rutinen har ugyldige felter")
    label = _safe_text(payload.get("label"), "Rutinenavn", MAX_LABEL_LENGTH)
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks or len(raw_tasks) > MAX_TASKS:
        raise DefinitionValidationError("Rutinen skal have mellem 1 og 30 trin")
    tasks = []
    seen_ids = set()
    allowed_fields = {"id", "title", "pictogram", "time", "weekdays"}
    for raw in raw_tasks:
        if not isinstance(raw, dict) or not set(raw).issubset(allowed_fields):
            raise DefinitionValidationError("Et trin har ugyldige felter")
        if require_ids and not raw.get("id"):
            raise DefinitionValidationError("Trin-ID mangler")
        task_id = _task_id(raw.get("id"), routine_id)
        if task_id in seen_ids:
            raise DefinitionValidationError("Trin-ID må ikke gentages")
        seen_ids.add(task_id)
        title = _safe_text(raw.get("title"), "Trintitel", MAX_TITLE_LENGTH)
        pictogram = raw.get("pictogram")
        if pictogram not in PICTOGRAM_LABELS:
            raise DefinitionValidationError("Piktogrammet er ugyldigt")
        raw_time = raw.get("time")
        guidance_time = None if raw_time in (None, "") else raw_time
        if guidance_time is not None and (not isinstance(guidance_time, str) or not TIME_RE.fullmatch(guidance_time)):
            raise DefinitionValidationError("Tidspunktet skal være HH:MM")
        raw_weekdays = raw.get("weekdays", [])
        if not isinstance(raw_weekdays, list):
            raise DefinitionValidationError("Ugedage er ugyldige")
        if any(not isinstance(day, int) or isinstance(day, bool) or day not in range(7) for day in raw_weekdays):
            raise DefinitionValidationError("Ugedage er ugyldige")
        if len(set(raw_weekdays)) != len(raw_weekdays):
            raise DefinitionValidationError("Ugedage må ikke gentages")
        tasks.append(RoutineTask(task_id, title, pictogram, guidance_time, tuple(sorted(raw_weekdays))))
    return RoutineDefinition(routine_id, label, tuple(tasks))


def definition_to_dict(definition):
    return {
        "label": definition.label,
        "tasks": [
            {
                "id": task.id,
                "title": task.title,
                "pictogram": task.pictogram,
                "time": task.time,
                "weekdays": list(task.weekdays),
            }
            for task in definition.tasks
        ],
    }


def tasks_for_date(definition, local_date):
    weekday = local_date.weekday()
    return tuple(task for task in definition.tasks if not task.weekdays or weekday in task.weekdays)


class RoutineDefinitionStore:
    def __init__(self, path=DEFAULT_DEFINITIONS_PATH):
        self.path = Path(path)
        self._lock = threading.RLock()

    def _defaults(self):
        return copy.deepcopy(DEFAULT_DEFINITIONS)

    def _read_unlocked(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or set(raw) != ROUTINE_IDS:
                raise DefinitionValidationError("Definitioner er ugyldige")
            return {
                routine_id: validate_definition(routine_id, raw[routine_id], require_ids=True)
                for routine_id in ROUTINE_IDS
            }
        except (FileNotFoundError, OSError, ValueError, TypeError, DefinitionValidationError):
            return self._defaults()

    def _write_unlocked(self, definitions):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="family_routine_definitions_",
            suffix=".tmp",
            dir=self.path.parent,
        )
        payload = {
            routine_id: definition_to_dict(definitions[routine_id])
            for routine_id in ("morning", "evening")
        }
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self.path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def all(self):
        with self._lock:
            return self._read_unlocked()

    def get(self, routine_id):
        if routine_id not in ROUTINE_IDS:
            raise KeyError(routine_id)
        return self.all()[routine_id]

    def update(self, routine_id, payload):
        if routine_id not in ROUTINE_IDS:
            raise KeyError(routine_id)
        normalized = validate_definition(routine_id, payload)
        with self._lock:
            definitions = self._read_unlocked()
            previous = definitions[routine_id]
            definitions[routine_id] = normalized
            self._write_unlocked(definitions)
            return previous, normalized

    def reset_default(self, routine_id):
        if routine_id not in ROUTINE_IDS:
            raise KeyError(routine_id)
        with self._lock:
            definitions = self._read_unlocked()
            previous = definitions[routine_id]
            restored = copy.deepcopy(DEFAULT_DEFINITIONS[routine_id])
            definitions[routine_id] = restored
            self._write_unlocked(definitions)
            return previous, restored
