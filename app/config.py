import os


def env_bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ["1", "true", "yes", "on"]


def env_int(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_positive_int(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def env_float(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def env_csv(name):
    value = os.getenv(name, "")
    return set([item.strip() for item in value.split(",") if item.strip()])


def normalize_asset_id(value, default_plugin="docker"):
    value = value.strip()
    if not value:
        return ""
    return value if ":" in value else f"{default_plugin}:{value}"


def env_relationships(name):
    """Parse ASSET_DEPENDENCIES style values.

    Format examples:
    ASSET_DEPENDENCIES=docker:app>docker:network,docker:worker>docker:database
    ASSET_DEPENDENCIES=app>network,worker>database
    """
    value = os.getenv(name, "")
    relationships = []
    for item in value.split(","):
        item = item.strip()
        if not item or ">" not in item:
            continue
        source, target = item.split(">", 1)
        source_id = normalize_asset_id(source)
        target_id = normalize_asset_id(target)
        if source_id and target_id:
            relationships.append((source_id, target_id))
    return relationships


def home_assistant_configuration():
    env_base_url = os.getenv("HOME_ASSISTANT_URL", "").strip()
    env_access_value = os.getenv("HOME_ASSISTANT_" + "TOKEN", "").strip()
    try:
        from app import settings_store

        base_url = settings_store.get_setting("home_assistant.base_url", env_base_url, db_path=DB_PATH).strip()
        access_value = settings_store.get_secret("home_assistant.token", env_access_value, db_path=DB_PATH)
    except (OSError, RuntimeError):
        base_url = env_base_url
        access_value = env_access_value
    return {
        "base_url": base_url,
        "access_value": access_value,
        "timeout_seconds": env_positive_int("HOME_ASSISTANT_TIMEOUT_SECONDS", 5),
    }


def weather_configuration():
    return {
        **home_assistant_configuration(),
        "entity_id": os.getenv("HOME_ASSISTANT_WEATHER_ENTITY", "").strip(),
        "cache_seconds": env_positive_int("WEATHER_CACHE_SECONDS", 120),
        "stale_seconds": env_positive_int("WEATHER_STALE_SECONDS", 3600),
    }


def calendar_configuration():
    return {
        "calendars": os.getenv("HOME_ASSISTANT_CALENDARS", "").strip(),
        "lookahead_days": env_positive_int("CALENDAR_LOOKAHEAD_DAYS", 7),
        "cache_seconds": env_positive_int("CALENDAR_CACHE_SECONDS", 300),
        "stale_seconds": env_positive_int("CALENDAR_STALE_SECONDS", 3600),
        "max_events": env_positive_int("CALENDAR_MAX_EVENTS", 40),
    }


def meal_plan_configuration():
    return {
        **home_assistant_configuration(),
        "entity_id": os.getenv("HOME_ASSISTANT_MEAL_CALENDAR", "calendar.madplan").strip(),
        "lookahead_days": env_positive_int("MEAL_PLAN_LOOKAHEAD_DAYS", 7),
        "cache_seconds": env_positive_int("MEAL_PLAN_CACHE_SECONDS", 300),
        "stale_seconds": env_positive_int("MEAL_PLAN_STALE_SECONDS", 3600),
        "max_events": env_positive_int("MEAL_PLAN_MAX_EVENTS", 20),
    }


def family_tasks_configuration():
    return {
        **home_assistant_configuration(),
        "sources": os.getenv(
            "HOME_ASSISTANT_TASK_LISTS",
            "todo.familieopgaver|Familieopgaver,todo.lektier|Lektier,todo.shopping_list|Indkøbsliste",
        ).strip(),
        "cache_seconds": env_positive_int("FAMILY_TASKS_CACHE_SECONDS", 60),
        "stale_seconds": env_positive_int("FAMILY_TASKS_STALE_SECONDS", 900),
        "max_items": env_positive_int("FAMILY_TASKS_MAX_ITEMS", 30),
    }


APP_NAME = os.getenv("APP_NAME", "Jarvis-os")
VERSION = "0.13.0"
SAFE_MODE = env_bool("SAFE_MODE", True)
RUN_INTERVAL_SECONDS = env_positive_int("RUN_INTERVAL_SECONDS", 15)
DRY_RUN = env_bool("DRY_RUN", True)
DB_PATH = os.getenv("DB_PATH", "/data/jarvis.db")

CRITICAL_SERVICES = env_csv("CRITICAL_SERVICES")
OPTIONAL_SERVICES = env_csv("OPTIONAL_SERVICES")
STOPPED_BY_DESIGN_SERVICES = env_csv("STOPPED_BY_DESIGN_SERVICES")
ASSET_DEPENDENCIES = env_relationships("ASSET_DEPENDENCIES")
AUTH_SESSION_MINUTES = env_positive_int("AUTH_SESSION_MINUTES", 720)
AUTH_COOKIE_SECURE = env_bool("AUTH_COOKIE_SECURE", False)
