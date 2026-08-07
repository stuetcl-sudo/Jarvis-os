import json

from fastapi import APIRouter
from pydantic import BaseModel

from app import config, settings_store


MODULES = ("calendar", "tasks", "routines", "meal_plan", "weather", "safety")
MODULE_SETTING_KEY = "family.modules.enabled"
DEFAULT_MODULE_SETTINGS = {module: True for module in MODULES}


class ModuleSettingsPayload(BaseModel):
    modules: dict[str, bool]


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


router = APIRouter(prefix="/api/admin/modules", tags=["admin modules"])


@router.get("")
def api_get_module_settings():
    return {"status": "ok", "modules": load_module_settings(db_path=config.DB_PATH)}


@router.post("")
def api_save_module_settings(payload: ModuleSettingsPayload):
    return {"status": "ok", "modules": save_module_settings(payload.modules, db_path=config.DB_PATH)}
