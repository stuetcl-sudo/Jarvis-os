import os


def env_bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ["1", "true", "yes", "on"]


def env_csv(name):
    value = os.getenv(name, "")
    return set([item.strip() for item in value.split(",") if item.strip()])


APP_NAME = os.getenv("APP_NAME", "Jarvis-os")
SAFE_MODE = env_bool("SAFE_MODE", True)
ALLOW_RESTART_STOPPED = env_bool("ALLOW_RESTART_STOPPED", True)
ALLOWED_RESTART_CONTAINERS = env_csv("ALLOWED_RESTART_CONTAINERS")
PROTECTED_CONTAINERS = env_csv("PROTECTED_CONTAINERS") or {"jarvis-os", "adguardhome", "caddy", "gluetun"}
DB_PATH = os.getenv("DB_PATH", "/data/jarvis.db")
