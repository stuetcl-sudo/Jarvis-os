from urllib.parse import quote

import httpx
from fastapi import APIRouter

from app import config, home_entity_settings
from app.home_assistant import HomeAssistantClient, HomeAssistantConfigurationError, HomeAssistantUnavailable, load_home_assistant_connection

SAFE_STATES = {"off", "closed", "idle", "standby"}
UNKNOWN_STATES = {"unavailable", "unknown", "none", ""}
CAMERA_PROBLEM_STATES = {"unavailable", "unknown", "none", "offline", ""}


class SafetyStatusConfigurationError(ValueError):
    pass


class SafetyStatusUnavailable(RuntimeError):
    pass


def status_item(status, label):
    return {"status": status, "label": label}


def load_safety_status_settings(db_path=None):
    try:
        connection = load_home_assistant_connection()
    except HomeAssistantConfigurationError as exc:
        raise SafetyStatusConfigurationError("Home Assistant safety configuration is invalid") from exc
    if connection is None:
        return None
    settings = home_entity_settings.load_entity_settings(db_path=db_path)
    return {
        "connection": connection,
        "doors": settings.get("safety_door_entities") or [],
        "motion": settings.get("safety_motion_entities") or [],
        "cameras": settings.get("safety_camera_entities") or [],
    }


def friendly_name(payload, fallback):
    attributes = payload.get("attributes") if isinstance(payload, dict) else {}
    if not isinstance(attributes, dict):
        attributes = {}
    return str(attributes.get("friendly_name") or fallback).strip() or fallback


def entity_state(payload):
    if not isinstance(payload, dict):
        return "unknown"
    return str(payload.get("state") or "unknown").strip().lower()


def door_status(entities, states):
    if not entities:
        return status_item("unknown", "Ikke valgt")
    open_items = []
    unknown_items = []
    for entity_id in entities:
        payload = states.get(entity_id)
        state = entity_state(payload)
        if state in UNKNOWN_STATES:
            unknown_items.append(entity_id)
        elif state not in SAFE_STATES:
            open_items.append(friendly_name(payload, entity_id))
    if open_items:
        return status_item("warning", f"{open_items[0]} åben" if len(open_items) == 1 else f"{len(open_items)} åbne")
    if unknown_items:
        return status_item("unknown", "Ukendt")
    return status_item("ok", "Lukket")


def motion_status(entities, states):
    if not entities:
        return status_item("unknown", "Ikke valgt")
    active = []
    unknown_items = []
    for entity_id in entities:
        payload = states.get(entity_id)
        state = entity_state(payload)
        if state in UNKNOWN_STATES:
            unknown_items.append(entity_id)
        elif state not in SAFE_STATES:
            active.append(friendly_name(payload, entity_id))
    if active:
        return status_item("warning", "Bevægelse" if len(active) == 1 else f"{len(active)} aktive")
    if unknown_items:
        return status_item("unknown", "Ukendt")
    return status_item("ok", "Roligt")


def camera_status(entities, states):
    if not entities:
        return status_item("unknown", "Ikke valgt")
    problem_count = sum(1 for entity_id in entities if entity_state(states.get(entity_id)) in CAMERA_PROBLEM_STATES)
    if problem_count == 0:
        return status_item("ok", "OK")
    if problem_count == 1:
        return status_item("warning", "1 offline")
    return status_item("critical", f"{problem_count} offline")


def normalize_safety_status(settings, states):
    return {
        "status": "ok",
        "internet": status_item("ok", "Online"),
        "doors": door_status(settings["doors"], states),
        "motion": motion_status(settings["motion"], states),
        "cameras": camera_status(settings["cameras"], states),
    }


class HomeAssistantSafetyStatusClient:
    def __init__(self, settings, client_factory=httpx.Client):
        self.settings = settings
        self.client_factory = client_factory

    def fetch(self):
        client = HomeAssistantClient(self.settings["connection"], self.client_factory)
        states = {}
        entity_ids = list(dict.fromkeys(self.settings["doors"] + self.settings["motion"] + self.settings["cameras"]))
        try:
            for entity_id in entity_ids:
                states[entity_id] = client.get_json(f"/api/states/{quote(entity_id, safe='')}")
        except HomeAssistantUnavailable as exc:
            raise SafetyStatusUnavailable("Home Assistant safety status is unavailable") from exc
        return normalize_safety_status(self.settings, states)


class SafetyStatusService:
    def __init__(self, settings_loader=load_safety_status_settings, client_factory=httpx.Client):
        self.settings_loader = settings_loader
        self.client_factory = client_factory

    def get_safety_status(self):
        try:
            settings = self.settings_loader(db_path=config.DB_PATH)
        except TypeError:
            settings = self.settings_loader()
        except SafetyStatusConfigurationError:
            return unavailable_status("Home Assistant er ikke klar")
        if settings is None:
            return unavailable_status("Home Assistant er ikke valgt")
        try:
            return HomeAssistantSafetyStatusClient(settings, self.client_factory).fetch()
        except SafetyStatusUnavailable:
            return unavailable_status("Home Assistant svarer ikke")


def unavailable_status(label):
    return {
        "status": "unknown",
        "internet": status_item("ok", "Online"),
        "doors": status_item("unknown", label),
        "motion": status_item("unknown", label),
        "cameras": status_item("unknown", label),
    }


safety_status_service = SafetyStatusService()
router = APIRouter()


@router.get("/api/family/safety-status")
def family_safety_status():
    return safety_status_service.get_safety_status()
