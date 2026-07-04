import json

from fastapi import APIRouter
from pydantic import BaseModel

from app import config, settings_store

ROLES = ("owner", "adult", "child", "wall_display")
FEATURES = ("calendar", "weather", "meal", "tasks", "safety")
ACTIONS = ("task_add", "task_complete", "task_edit", "task_remove")
VISIBILITY_SETTING_KEY = "family.visibility.rules"
ACTION_SETTING_KEY = "family.action.rules"

DEFAULT_VISIBILITY = {
    role: {feature: True for feature in FEATURES}
    for role in ROLES
}
DEFAULT_ACTIONS = {
    "owner": {action: True for action in ACTIONS},
    "adult": {action: True for action in ACTIONS},
    "child": {
        "task_add": False,
        "task_complete": True,
        "task_edit": False,
        "task_remove": False,
    },
    "wall_display": {
        "task_add": False,
        "task_complete": False,
        "task_edit": False,
        "task_remove": False,
    },
}


class FamilyVisibilityPayload(BaseModel):
    rules: dict[str, dict[str, bool]]


class FamilyActionPayload(BaseModel):
    rules: dict[str, dict[str, bool]]


def _clone(value):
    return json.loads(json.dumps(value))


def normalize_visibility_rules(value):
    source = value if isinstance(value, dict) else {}
    rules = _clone(DEFAULT_VISIBILITY)
    for role in ROLES:
        supplied_role = source.get(role)
        if not isinstance(supplied_role, dict):
            continue
        for feature in FEATURES:
            if feature in supplied_role:
                rules[role][feature] = bool(supplied_role.get(feature))
    rules["owner"] = {feature: True for feature in FEATURES}
    return rules


def normalize_action_rules(value):
    source = value if isinstance(value, dict) else {}
    rules = _clone(DEFAULT_ACTIONS)
    for role in ROLES:
        supplied_role = source.get(role)
        if not isinstance(supplied_role, dict):
            continue
        for action in ACTIONS:
            if action in supplied_role:
                rules[role][action] = bool(supplied_role.get(action))
    rules["owner"] = {action: True for action in ACTIONS}
    return rules


def _load_json_setting(key, normalizer, db_path=None):
    raw = settings_store.get_setting(key, "", db_path=db_path)
    if not raw:
        return normalizer({})
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return normalizer({})
    return normalizer(parsed)


def load_visibility_rules(db_path=None):
    return _load_json_setting(VISIBILITY_SETTING_KEY, normalize_visibility_rules, db_path=db_path)


def load_action_rules(db_path=None):
    return _load_json_setting(ACTION_SETTING_KEY, normalize_action_rules, db_path=db_path)


def _save_json_setting(key, rules, normalizer, db_path=None):
    normalized = normalizer(rules)
    settings_store.set_setting(
        key,
        json.dumps(normalized, sort_keys=True, separators=(",", ":")),
        db_path=db_path,
    )
    return normalized


def save_visibility_rules(rules, db_path=None):
    return _save_json_setting(VISIBILITY_SETTING_KEY, rules, normalize_visibility_rules, db_path=db_path)


def save_action_rules(rules, db_path=None):
    return _save_json_setting(ACTION_SETTING_KEY, rules, normalize_action_rules, db_path=db_path)


def role_can_see(role, feature, rules=None):
    if role == "owner":
        return True
    if role not in ROLES or feature not in FEATURES:
        return False
    active_rules = rules or load_visibility_rules(db_path=config.DB_PATH)
    return bool(active_rules.get(role, {}).get(feature, True))


def role_can_do(role, action, rules=None):
    if role == "owner":
        return True
    if role not in ROLES or action not in ACTIONS:
        return False
    active_rules = rules or load_action_rules(db_path=config.DB_PATH)
    return bool(active_rules.get(role, {}).get(action, False))


router = APIRouter()


@router.get("/api/admin/family-visibility")
def api_get_family_visibility():
    return {"status": "ok", "roles": list(ROLES), "features": list(FEATURES), "rules": load_visibility_rules(db_path=config.DB_PATH)}


@router.post("/api/admin/family-visibility")
def api_save_family_visibility(payload: FamilyVisibilityPayload):
    return {"status": "ok", "rules": save_visibility_rules(payload.rules, db_path=config.DB_PATH)}


@router.get("/api/admin/family-actions")
def api_get_family_actions():
    return {"status": "ok", "roles": list(ROLES), "actions": list(ACTIONS), "rules": load_action_rules(db_path=config.DB_PATH)}


@router.post("/api/admin/family-actions")
def api_save_family_actions(payload: FamilyActionPayload):
    return {"status": "ok", "rules": save_action_rules(payload.rules, db_path=config.DB_PATH)}
