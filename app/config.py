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
    return {
        "base_url": os.getenv("HOME_ASSISTANT_URL", "").strip(),
        "access_value": os.getenv("HOME_ASSISTANT_" + "TOKEN", "").strip(),
        "timeout_seconds": env_positive_int("HOME_ASSISTANT_TIMEOUT_SECONDS", 5),
    }


def weather_configuration():
    return {
        **home_assistant_configuration(),
        "entity_id": os.getenv("HOME_ASSISTANT_WEATHER_ENTITY", "").strip(),
        "cache_seconds": env_positive_int("WEATHER_CACHE_SECONDS", 300),
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


APP_NAME = os.getenv("APP_NAME", "Jarvis-os")
VERSION = "0.9.0"
SAFE_MODE = env_bool("SAFE_MODE", True)
ALLOW_RESTART_STOPPED = env_bool("ALLOW_RESTART_STOPPED", True)
WORKER_ENABLED = env_bool("WORKER_ENABLED", True)
WORKER_INTERVAL_SECONDS = env_int("WORKER_INTERVAL_SECONDS", 60)
AUTO_START_FAILURE_LIMIT = env_int("AUTO_START_FAILURE_LIMIT", 3)
AUTO_START_FAILURE_WINDOW_MINUTES = env_int("AUTO_START_FAILURE_WINDOW_MINUTES", 30)
DB_PATH = os.getenv("DB_PATH", "/data/jarvis.db")
ROUTINE_TIMEZONE = os.getenv("ROUTINE_TIMEZONE", "Europe/Copenhagen").strip() or "Europe/Copenhagen"

AUTH_COOKIE_SECURE = env_bool("AUTH_COOKIE_SECURE", False)
AUTH_SESSION_HOURS = env_positive_int("AUTH_SESSION_HOURS", 12)
AUTH_WALL_SESSION_DAYS = env_positive_int("AUTH_WALL_SESSION_DAYS", 30)
AUTH_LOGIN_MAX_FAILURES = env_positive_int("AUTH_LOGIN_MAX_FAILURES", 5)
AUTH_LOGIN_WINDOW_MINUTES = env_positive_int("AUTH_LOGIN_WINDOW_MINUTES", 15)

CRITICAL_SERVICES = env_csv("CRITICAL_SERVICES") or {"jarvis-os"}
PROTECTED_CONTAINERS = env_csv("PROTECTED_CONTAINERS") or {"jarvis-os"}
OPTIONAL_SERVICES = env_csv("OPTIONAL_SERVICES")
IGNORED_SERVICES = env_csv("IGNORED_SERVICES")
ALLOWED_RESTART_CONTAINERS = env_csv("ALLOWED_RESTART_CONTAINERS")
ALLOWED_AUTO_START_CONTAINERS = env_csv("ALLOWED_AUTO_START_CONTAINERS")
ASSET_DEPENDENCIES = env_relationships("ASSET_DEPENDENCIES")

CPU_WARN_PERCENT = env_int("CPU_WARN_PERCENT", 90)
MEMORY_WARN_PERCENT = env_int("MEMORY_WARN_PERCENT", 90)
SWAP_WARN_PERCENT = env_int("SWAP_WARN_PERCENT", 80)
DISK_WARN_PERCENT = env_int("DISK_WARN_PERCENT", 85)

BASELINE_MIN_SAMPLES = env_int("BASELINE_MIN_SAMPLES", 20)
BASELINE_MAX_STEP_PERCENT = env_float("BASELINE_MAX_STEP_PERCENT", 2.0)
ANOMALY_RAM_DELTA_PERCENT = env_float("ANOMALY_RAM_DELTA_PERCENT", 20.0)
ANOMALY_SWAP_DELTA_PERCENT = env_float("ANOMALY_SWAP_DELTA_PERCENT", 20.0)
DISK_TREND_DELTA_PERCENT = env_float("DISK_TREND_DELTA_PERCENT", 2.0)

OBSERVATIONS_RETENTION_DAYS = env_int("OBSERVATIONS_RETENTION_DAYS", 30)
WORKER_CHECKS_RETENTION_DAYS = env_int("WORKER_CHECKS_RETENTION_DAYS", 30)
ACTION_LOG_RETENTION_DAYS = env_int("ACTION_LOG_RETENTION_DAYS", 90)
RESOLVED_INCIDENTS_RETENTION_DAYS = env_int("RESOLVED_INCIDENTS_RETENTION_DAYS", 90)
