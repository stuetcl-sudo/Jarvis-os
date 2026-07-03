from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import config, home_assistant_setup, home_entity_settings, home_setup, settings_store


router = APIRouter(prefix="/api/admin/setup", tags=["setup"])


class HomeAssistantConnectionPayload(BaseModel):
    base_url: str
    token: str = ""


class HomeAssistantEntitySettingsPayload(BaseModel):
    calendar_entities: list[str] = []
    meal_calendar: str = ""
    task_entities: list[str] = []
    weather_entity: str = ""
    electricity_price_entity: str = ""
    power_entity: str = ""
    energy_entity: str = ""
    temperature_entities: list[str] = []
    humidity_entities: list[str] = []


class HomeSettingsPayload(BaseModel):
    home_name: str
    timezone: str
    owner_name: str


def _connection_values(payload=None):
    current = config.home_assistant_configuration()
    base_url = payload.base_url if payload else current["base_url"]
    token = payload.token.strip() if payload and payload.token.strip() else current["access_value"]
    return base_url, token, current["timeout_seconds"]


@router.get("/summary")
def get_setup_summary():
    summary = home_setup.setup_summary(db_path=config.DB_PATH)
    summary["home_assistant"] = home_assistant_summary()
    return summary


@router.get("/home")
def get_home_settings():
    return home_setup.load_home_settings(db_path=config.DB_PATH)


@router.post("/home")
def save_home_settings(payload: HomeSettingsPayload):
    try:
        return home_setup.save_home_settings(
            payload.home_name,
            payload.timezone,
            payload.owner_name,
            db_path=config.DB_PATH,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/complete")
def complete_setup():
    try:
        return home_setup.complete_setup(db_path=config.DB_PATH)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/home-assistant")
def home_assistant_summary():
    summary = settings_store.public_connection_summary(db_path=config.DB_PATH)
    if not summary["home_assistant_url"]:
        summary["home_assistant_url"] = config.home_assistant_configuration()["base_url"]
    summary["configured"] = bool(
        summary["home_assistant_url"]
        and (
            summary["home_assistant_token_configured"]
            or bool(config.home_assistant_configuration()["access_value"])
        )
    )
    return summary


@router.post("/home-assistant/test")
def test_home_assistant_connection(payload: HomeAssistantConnectionPayload):
    base_url, token, timeout_seconds = _connection_values(payload)
    try:
        return home_assistant_setup.test_connection(base_url, token, timeout_seconds)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/home-assistant/save")
def save_home_assistant_connection(payload: HomeAssistantConnectionPayload):
    base_url, token, timeout_seconds = _connection_values(payload)
    try:
        result = home_assistant_setup.test_connection(base_url, token, timeout_seconds)
        summary = home_assistant_setup.save_connection(base_url, token, db_path=config.DB_PATH)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {**summary, **result}


@router.post("/home-assistant/entities")
def discover_home_assistant_entities(payload: HomeAssistantConnectionPayload):
    base_url, token, timeout_seconds = _connection_values(payload)
    try:
        entities = home_assistant_setup.discover_entities(base_url, token, timeout_seconds)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"entities": entities, "count": len(entities)}


@router.get("/home-assistant/entity-settings")
def get_home_assistant_entity_settings():
    return home_entity_settings.load_entity_settings(db_path=config.DB_PATH)


@router.post("/home-assistant/entity-settings")
def save_home_assistant_entity_settings(payload: HomeAssistantEntitySettingsPayload):
    try:
        return home_entity_settings.save_entity_settings(payload.model_dump(), db_path=config.DB_PATH)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
