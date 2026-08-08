import json
import os
import re

from app import settings_store


ENTITY_ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")

SINGLE_FIELDS = {
    "meal_calendar": ("home_assistant.meal_calendar", {"calendar"}),
    "weather_entity": ("home_assistant.weather_entity", {"weather"}),
    "internet_status_entity": ("home_assistant.internet_status_entity", {"binary_sensor", "sensor"}),
    "electricity_price_entity": ("home_assistant.electricity_price_entity", {"sensor"}),
    "power_entity": ("home_assistant.power_entity", {"sensor"}),
    "energy_entity": ("home_assistant.energy_entity", {"sensor"}),
}

LIST_FIELDS = {
    "calendar_entities": ("home_assistant.calendar_entities", {"calendar"}),
    "task_entities": ("home_assistant.task_entities", {"todo"}),
    "temperature_entities": ("home_assistant.temperature_entities", {"sensor"}),
    "humidity_entities": ("home_assistant.humidity_entities", {"sensor"}),
    "safety_door_entities": ("home_assistant.safety_door_entities", {"binary_sensor"}),
    "safety_motion_entities": ("home_assistant.safety_motion_entities", {"binary_sensor"}),
    "safety_camera_entities": ("home_assistant.safety_camera_entities", {"camera"}),
}

LEGACY_TASK_SOURCES = (
    "todo.familieopgaver|Familieopgaver,todo.lektier|Lektier,"
    "todo.shopping_list|Indkøbsliste"
)


def _validate_entity_id(value, allowed_types):
    entity_id = str(value or "").strip()
    if not entity_id:
        return ""
    if not ENTITY_ID_PATTERN.fullmatch(entity_id):
        raise ValueError(f"Ugyldigt Home Assistant-entitets-id: {entity_id}")
    entity_type = entity_id.split(".", 1)[0]
    if allowed_types and entity_type not in allowed_types:
        expected = ", ".join(sorted(allowed_types))
        raise ValueError(f"{entity_id} skal være af typen {expected}")
    return entity_id


def _load_list(key, db_path=None):
    raw = settings_store.get_setting(key, "[]", db_path=db_path)
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def runtime_entity_setting(field, fallback, db_path=None):
    """Return a saved entity selection, falling back only when no DB row exists."""
    definitions = {**SINGLE_FIELDS, **LIST_FIELDS}
    if field not in definitions:
        raise KeyError(field)
    key = definitions[field][0]
    missing = object()
    raw = settings_store.get_setting(key, missing, db_path=db_path)
    if raw is missing:
        return fallback
    if field in SINGLE_FIELDS:
        return str(raw or "").strip()
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and item.strip()]


def _legacy_list(raw_value, allowed_types):
    result = []
    for entry in str(raw_value or "").split(","):
        entity_id = entry.split("|", 1)[0].strip()
        if (
            entity_id
            and ENTITY_ID_PATTERN.fullmatch(entity_id)
            and entity_id.split(".", 1)[0] in allowed_types
            and entity_id not in result
        ):
            result.append(entity_id)
    return result


def legacy_entity_settings():
    weather = os.getenv("HOME_ASSISTANT_WEATHER_ENTITY", "").strip()
    meal = os.getenv("HOME_ASSISTANT_MEAL_CALENDAR", "calendar.madplan").strip()
    return {
        "meal_calendar": meal if ENTITY_ID_PATTERN.fullmatch(meal) and meal.startswith("calendar.") else "",
        "weather_entity": weather if ENTITY_ID_PATTERN.fullmatch(weather) and weather.startswith("weather.") else "",
        "calendar_entities": _legacy_list(os.getenv("HOME_ASSISTANT_CALENDARS", ""), {"calendar"}),
        "task_entities": _legacy_list(os.getenv("HOME_ASSISTANT_TASK_LISTS", LEGACY_TASK_SOURCES), {"todo"}),
    }


def load_effective_entity_settings(db_path=None):
    """Return values for editing without turning absent legacy settings into clears."""
    legacy = legacy_entity_settings()
    result = {}
    for field in SINGLE_FIELDS:
        result[field] = runtime_entity_setting(field, legacy.get(field, ""), db_path=db_path)
    for field in LIST_FIELDS:
        result[field] = runtime_entity_setting(field, legacy.get(field, []), db_path=db_path)
    return result


def load_entity_settings(db_path=None):
    result = {}
    for field, (key, _allowed_types) in SINGLE_FIELDS.items():
        result[field] = settings_store.get_setting(key, "", db_path=db_path)
    for field, (key, _allowed_types) in LIST_FIELDS.items():
        result[field] = _load_list(key, db_path=db_path)
    return result


def save_entity_settings(values, db_path=None):
    if not isinstance(values, dict):
        raise ValueError("Home Assistant-indstillinger skal være et objekt")

    for field, (key, allowed_types) in SINGLE_FIELDS.items():
        if field not in values:
            continue
        entity_id = _validate_entity_id(values.get(field), allowed_types)
        settings_store.set_setting(key, entity_id, db_path=db_path)

    for field, (key, allowed_types) in LIST_FIELDS.items():
        if field not in values:
            continue
        raw_items = values.get(field) or []
        if not isinstance(raw_items, list):
            raise ValueError(f"{field} skal være en liste")
        clean_items = []
        for item in raw_items:
            entity_id = _validate_entity_id(item, allowed_types)
            if entity_id and entity_id not in clean_items:
                clean_items.append(entity_id)
        settings_store.set_setting(key, json.dumps(clean_items), db_path=db_path)

    return load_entity_settings(db_path=db_path)
