import json
import re

from app import settings_store


ENTITY_ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")

SINGLE_FIELDS = {
    "meal_calendar": ("home_assistant.meal_calendar", {"calendar"}),
    "weather_entity": ("home_assistant.weather_entity", {"weather"}),
    "electricity_price_entity": ("home_assistant.electricity_price_entity", {"sensor"}),
    "power_entity": ("home_assistant.power_entity", {"sensor"}),
    "energy_entity": ("home_assistant.energy_entity", {"sensor"}),
}

LIST_FIELDS = {
    "calendar_entities": ("home_assistant.calendar_entities", {"calendar"}),
    "task_entities": ("home_assistant.task_entities", {"todo"}),
    "temperature_entities": ("home_assistant.temperature_entities", {"sensor"}),
    "humidity_entities": ("home_assistant.humidity_entities", {"sensor"}),
}


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


def load_entity_settings(db_path=None):
    result = {}
    for field, (key, _allowed_types) in SINGLE_FIELDS.items():
        result[field] = settings_store.get_setting(key, "", db_path=db_path)
    for field, (key, _allowed_types) in LIST_FIELDS.items():
        result[field] = _load_list(key, db_path=db_path)
    return result


def save_entity_settings(values, db_path=None):
    saved = {}
    for field, (key, allowed_types) in SINGLE_FIELDS.items():
        entity_id = _validate_entity_id(values.get(field, ""), allowed_types)
        settings_store.set_setting(key, entity_id, db_path=db_path)
        saved[field] = entity_id

    for field, (key, allowed_types) in LIST_FIELDS.items():
        raw_items = values.get(field, []) or []
        if not isinstance(raw_items, list):
            raise ValueError(f"{field} skal være en liste")
        clean_items = []
        for item in raw_items:
            entity_id = _validate_entity_id(item, allowed_types)
            if entity_id and entity_id not in clean_items:
                clean_items.append(entity_id)
        settings_store.set_setting(key, json.dumps(clean_items), db_path=db_path)
        saved[field] = clean_items
    return saved
