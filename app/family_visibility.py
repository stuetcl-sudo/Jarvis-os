import json

from fastapi import APIRouter
from pydantic import BaseModel

from app import config, settings_store

ROLES = ("owner", "adult", "child", "wall_display")
FEATURES = ("calendar", "weather", "meal", "tasks", "safety")
SETTING_KEY = "family.visibility.rules"

DEFAULT_VISIBILITY = {
    role: {feature: True for feature in FEATURES}
    for role in ROLES
}


class FamilyVisibilityPayload(BaseModel):
    rules: dict[str, dict[str, bool]]


def normalize_visibility_rules(value):
    source = value if isinstance(value, dict) else {}
    rules = json.loads(json.dumps(DEFAULT_VISIBILITY))
    for role in ROLES:
        supplied_role = source.get(role)
        if not isinstance(supplied_role, dict):
            continue
        for feature in FEATURES:
            if feature in supplied_role:
                rules[role][feature] = bool(supplied_role.get(feature))
    rules["owner"] = {feature: True for feature in FEATURES}
    return rules


def load_visibility_rules(db_path=None):
    raw = settings_store.get_setting(SETTING_KEY, "", db_path=db_path)
    if not raw:
        return normalize_visibility_rules({})
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return normalize_visibility_rules({})
    return normalize_visibility_rules(parsed)


def save_visibility_rules(rules, db_path=None):
    normalized = normalize_visibility_rules(rules)
    settings_store.set_setting(
        SETTING_KEY,
        json.dumps(normalized, sort_keys=True, separators=(",", ":")),
        db_path=db_path,
    )
    return normalized


def role_can_see(role, feature, rules=None):
    if role == "owner":
        return True
    if role not in ROLES or feature not in FEATURES:
        return False
    active_rules = rules or load_visibility_rules(db_path=config.DB_PATH)
    return bool(active_rules.get(role, {}).get(feature, True))


router = APIRouter()


@router.get("/api/admin/family-visibility")
def api_get_family_visibility():
    return {"status": "ok", "roles": list(ROLES), "features": list(FEATURES), "rules": load_visibility_rules(db_path=config.DB_PATH)}


@router.post("/api/admin/family-visibility")
def api_save_family_visibility(payload: FamilyVisibilityPayload):
    return {"status": "ok", "rules": save_visibility_rules(payload.rules, db_path=config.DB_PATH)}
