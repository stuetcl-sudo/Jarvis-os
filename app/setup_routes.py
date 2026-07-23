from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from app import (
    config,
    home_assistant_setup,
    home_entity_settings,
    home_setup,
    managed_home_assistant_installer,
    settings_store,
)
from app.setup_state import setup_status


router = APIRouter(prefix="/api/admin/setup", tags=["setup"])


@router.get("/status")
def get_setup_status():
    return setup_status(db_path=config.DB_PATH)


class HomeAssistantEntitySettingsPayload(BaseModel):
    calendar_entities: list[str] = Field(default_factory=list)
    meal_calendar: str = ""
    task_entities: list[str] = Field(default_factory=list)
    weather_entity: str = ""
    internet_status_entity: str = ""
    electricity_price_entity: str = ""
    power_entity: str = ""
    energy_entity: str = ""
    temperature_entities: list[str] = Field(default_factory=list)
    humidity_entities: list[str] = Field(default_factory=list)
    safety_door_entities: list[str] = Field(default_factory=list)
    safety_motion_entities: list[str] = Field(default_factory=list)
    safety_camera_entities: list[str] = Field(default_factory=list)


class HomeSettingsPayload(BaseModel):
    home_name: str
    timezone: str
    owner_name: str


def _connection_values(payload=None):
    current = config.home_assistant_configuration()
    if payload is not None and not isinstance(payload, dict):
        raise home_assistant_setup.HomeAssistantSetupError(
            "malformed_request", "Anmodningen om Home Assistant-forbindelsen er ugyldig"
        )
    base_url = payload.get("base_url", "") if payload is not None else current["base_url"]
    supplied_token = payload.get("token", "") if payload is not None else ""
    if not isinstance(base_url, str):
        raise home_assistant_setup.HomeAssistantSetupError(
            "malformed_url", "Home Assistant-adressen er ugyldig"
        )
    if len(base_url) > 2048:
        raise home_assistant_setup.HomeAssistantSetupError(
            "malformed_url", "Home Assistant-adressen er ugyldig"
        )
    if not isinstance(supplied_token, str):
        raise home_assistant_setup.HomeAssistantSetupError(
            "token_invalid", "Home Assistant-tokenet er ugyldigt"
        )
    token = supplied_token.strip() if supplied_token.strip() else current["access_value"]
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
    summary["token_configured"] = summary["home_assistant_token_configured"] or bool(
        config.home_assistant_configuration()["access_value"]
    )
    return summary


@router.get("/home-assistant/managed")
def managed_home_assistant_status():
    try:
        return managed_home_assistant_installer.managed_install_status(db_path=config.DB_PATH)
    except (OSError, RuntimeError) as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "managed_install_status_unavailable",
                "message": "Status for den administrerede Home Assistant-installation kunne ikke hentes.",
            },
        ) from exc


@router.post("/home-assistant/managed/plan")
def request_managed_home_assistant_plan(payload: object = Body(default=None)):
    try:
        return managed_home_assistant_installer.request_install_plan(payload, db_path=config.DB_PATH)
    except managed_home_assistant_installer.ManagedInstallError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except (OSError, RuntimeError) as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "managed_install_plan_unavailable",
                "message": "Installationsplanen kunne ikke gemmes.",
            },
        ) from exc


def _ha_error(exc):
    if isinstance(exc, home_assistant_setup.HomeAssistantSetupError):
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    raise HTTPException(
        status_code=400,
        detail={"code": "configuration_error", "message": "Home Assistant-konfigurationen kunne ikke bruges"},
    ) from exc


@router.post("/home-assistant/test")
def test_home_assistant_connection(payload: object = Body(...)):
    try:
        base_url, token, timeout_seconds = _connection_values(payload)
        return home_assistant_setup.test_connection(base_url, token, timeout_seconds)
    except (ValueError, RuntimeError) as exc:
        _ha_error(exc)


@router.post("/home-assistant/save")
def save_home_assistant_connection(payload: object = Body(...)):
    try:
        base_url, token, timeout_seconds = _connection_values(payload)
        result = home_assistant_setup.test_connection(base_url, token, timeout_seconds)
        summary = home_assistant_setup.save_connection(base_url, token, db_path=config.DB_PATH)
    except (ValueError, RuntimeError) as exc:
        _ha_error(exc)
    return {**summary, **result, "setup": setup_status(db_path=config.DB_PATH)}


@router.post("/home-assistant/entities")
def discover_home_assistant_entities(payload: object = Body(...)):
    try:
        base_url, token, timeout_seconds = _connection_values(payload)
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
        values = payload.model_dump(exclude_unset=True)
        return home_entity_settings.save_entity_settings(values, db_path=config.DB_PATH)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
