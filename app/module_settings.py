import json

from fastapi import APIRouter
from pydantic import BaseModel

from app import config, settings_store


MODULES = ("calendar", "tasks", "routines", "meal_plan", "weather", "safety")
MODULE_SETTING_KEY = "family.modules.enabled"
MODULE_CONFIG_SETTING_KEY = "family.modules.config"
DEFAULT_MODULE_SETTINGS = {module: True for module in MODULES}
DEFAULT_MODULE_CONFIG = {"calendar_days": 3, "meal_plan_days": 7, "weather_uv_enabled": True}


class ModuleSettingsPayload(BaseModel):
    modules: dict[str, bool]
    config: dict[str, int | bool] | None = None


def normalize_module_settings(value):
    source = value if isinstance(value, dict) else {}
    return {
        module: bool(source[module]) if module in source else True
        for module in MODULES
    }


def load_module_settings(db_path=None):
    try:
        raw = settings_store.get_setting(MODULE_SETTING_KEY, "", db_path=db_path)
    except OSError:
        return dict(DEFAULT_MODULE_SETTINGS)
    if not raw:
        return dict(DEFAULT_MODULE_SETTINGS)
    try:
        return normalize_module_settings(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        return dict(DEFAULT_MODULE_SETTINGS)


def save_module_settings(modules, db_path=None):
    normalized = normalize_module_settings(modules)
    settings_store.set_setting(
        MODULE_SETTING_KEY,
        json.dumps(normalized, sort_keys=True, separators=(",", ":")),
        db_path=db_path,
    )
    return normalized


def normalize_module_config(value):
    source = value if isinstance(value, dict) else {}
    result = dict(DEFAULT_MODULE_CONFIG)
    for key in ("calendar_days", "meal_plan_days"):
        candidate = source.get(key)
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            result[key] = max(1, min(7, candidate))
    if isinstance(source.get("weather_uv_enabled"), bool):
        result["weather_uv_enabled"] = source["weather_uv_enabled"]
    return result


def load_module_config(db_path=None):
    try:
        raw = settings_store.get_setting(MODULE_CONFIG_SETTING_KEY, "", db_path=db_path)
    except OSError:
        return dict(DEFAULT_MODULE_CONFIG)
    if not raw:
        return dict(DEFAULT_MODULE_CONFIG)
    try:
        return normalize_module_config(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        return dict(DEFAULT_MODULE_CONFIG)


def save_module_config(value, db_path=None):
    normalized = normalize_module_config(value)
    settings_store.set_setting(MODULE_CONFIG_SETTING_KEY, json.dumps(normalized, sort_keys=True, separators=(",", ":")), db_path=db_path)
    return normalized


router = APIRouter(prefix="/api/admin/modules", tags=["admin modules"])


@router.get("")
def api_get_module_settings():
    return {"status": "ok", "modules": load_module_settings(db_path=config.DB_PATH), "config": load_module_config(db_path=config.DB_PATH)}


@router.post("")
def api_save_module_settings(payload: ModuleSettingsPayload):
    modules = save_module_settings(payload.modules, db_path=config.DB_PATH)
    module_config = load_module_config(db_path=config.DB_PATH)
    if payload.config is not None:
        module_config = save_module_config({**module_config, **payload.config}, db_path=config.DB_PATH)
    return {"status": "ok", "modules": modules, "config": module_config}
