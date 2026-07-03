from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import home_entity_settings, settings_store


HOME_NAME_KEY = "home.name"
TIMEZONE_KEY = "home.timezone"
OWNER_NAME_KEY = "home.owner_name"
SETUP_COMPLETE_KEY = "setup.completed"


def _clean_text(value, field_name, maximum=80):
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} skal udfyldes")
    if len(text) > maximum:
        raise ValueError(f"{field_name} må højst være {maximum} tegn")
    return text


def validate_timezone(value):
    timezone = _clean_text(value, "Tidszone", 80)
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Tidszonen blev ikke genkendt") from exc
    return timezone


def load_home_settings(db_path=None):
    return {
        "home_name": settings_store.get_setting(HOME_NAME_KEY, "", db_path=db_path),
        "timezone": settings_store.get_setting(TIMEZONE_KEY, "Europe/Copenhagen", db_path=db_path),
        "owner_name": settings_store.get_setting(OWNER_NAME_KEY, "", db_path=db_path),
        "completed": settings_store.get_setting(SETUP_COMPLETE_KEY, "false", db_path=db_path) == "true",
    }


def save_home_settings(home_name, timezone, owner_name, db_path=None):
    values = {
        "home_name": _clean_text(home_name, "Hjemmets navn"),
        "timezone": validate_timezone(timezone),
        "owner_name": _clean_text(owner_name, "Ejerens navn"),
    }
    settings_store.set_setting(HOME_NAME_KEY, values["home_name"], db_path=db_path)
    settings_store.set_setting(TIMEZONE_KEY, values["timezone"], db_path=db_path)
    settings_store.set_setting(OWNER_NAME_KEY, values["owner_name"], db_path=db_path)
    return {**values, "completed": load_home_settings(db_path=db_path)["completed"]}


def setup_summary(db_path=None):
    home = load_home_settings(db_path=db_path)
    entities = home_entity_settings.load_entity_settings(db_path=db_path)
    selected_count = 0
    for value in entities.values():
        if isinstance(value, list):
            selected_count += len(value)
        elif value:
            selected_count += 1
    return {
        **home,
        "selected_entity_count": selected_count,
        "ready_to_complete": bool(home["home_name"] and home["owner_name"] and home["timezone"]),
    }


def complete_setup(db_path=None):
    summary = setup_summary(db_path=db_path)
    if not summary["ready_to_complete"]:
        raise ValueError("Udfyld hjemmets navn, tidszone og ejer, før opsætningen afsluttes")
    settings_store.set_setting(SETUP_COMPLETE_KEY, "true", db_path=db_path)
    return setup_summary(db_path=db_path)
