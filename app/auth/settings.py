import os

from app import config


def positive_int(name, default):
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


def strict_bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def apply_auth_settings():
    config.AUTH_COOKIE_SECURE = strict_bool("AUTH_COOKIE_SECURE", False)
    config.AUTH_SESSION_HOURS = positive_int("AUTH_SESSION_HOURS", 12)
    config.AUTH_WALL_SESSION_DAYS = positive_int("AUTH_WALL_SESSION_DAYS", 30)
    config.AUTH_LOGIN_MAX_FAILURES = positive_int("AUTH_LOGIN_MAX_FAILURES", 5)
    config.AUTH_LOGIN_WINDOW_MINUTES = positive_int("AUTH_LOGIN_WINDOW_MINUTES", 15)


apply_auth_settings()
