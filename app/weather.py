import copy
import math
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import APIRouter

from app import config

SUPPORTED_CONDITIONS = {
    "clear-night",
    "cloudy",
    "fog",
    "hail",
    "lightning",
    "lightning-rainy",
    "partlycloudy",
    "pouring",
    "rainy",
    "snowy",
    "snowy-rainy",
    "sunny",
    "windy",
    "windy-variant",
    "exceptional",
}
WEATHER_ENTITY_RE = re.compile(r"^weather\.[a-z0-9_]+$")
PUBLIC_FIELDS = {
    "status",
    "condition",
    "temperature",
    "temperature_unit",
    "apparent_temperature",
    "humidity",
    "wind_speed",
    "wind_speed_unit",
    "forecast",
    "updated_at",
    "stale",
}
FORECAST_FIELDS = {
    "datetime",
    "condition",
    "temperature_high",
    "temperature_low",
    "precipitation_probability",
}


class WeatherConfigurationError(ValueError):
    pass


class WeatherUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class WeatherSettings:
    base_url: str
    access_value: str = field(repr=False)
    entity_id: str
    timeout_seconds: int
    cache_seconds: int
    stale_seconds: int


def load_weather_settings() -> WeatherSettings | None:
    try:
        values = config.weather_configuration()
    except ValueError as exc:
        raise WeatherConfigurationError("Home Assistant weather configuration is invalid") from exc

    raw_url = values["base_url"]
    access_value = values["access_value"]
    entity_id = values["entity_id"]
    timeout_seconds = values["timeout_seconds"]
    cache_seconds = values["cache_seconds"]
    stale_seconds = values["stale_seconds"]

    if not raw_url and not access_value and not entity_id:
        return None
    if not raw_url or not access_value or not entity_id:
        raise WeatherConfigurationError("Home Assistant weather configuration is incomplete")

    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise WeatherConfigurationError("Home Assistant URL must use http or https")
    if parsed.username is not None or parsed.password is not None:
        raise WeatherConfigurationError("Home Assistant URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise WeatherConfigurationError("Home Assistant URL must not contain query or fragment")
    base_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")).rstrip("/")
    if not WEATHER_ENTITY_RE.fullmatch(entity_id):
        raise WeatherConfigurationError("Configured entity must be a weather entity")
    if stale_seconds < cache_seconds:
        raise WeatherConfigurationError("WEATHER_STALE_SECONDS must be at least WEATHER_CACHE_SECONDS")
    return WeatherSettings(base_url, access_value, entity_id, timeout_seconds, cache_seconds, stale_seconds)


def _safe_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _condition(value):
    text = str(value or "").strip().lower()
    return text if text in SUPPORTED_CONDITIONS else "exceptional"


def _utc_iso(value=None, use_now=False):
    if value in (None, ""):
        if not use_now:
            return None
        current = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        current = value
    elif isinstance(value, date):
        current = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    else:
        text = str(value).strip()
        try:
            current = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed_date = date.fromisoformat(text)
            except ValueError:
                return None
            current = datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _forecast_container(payload, entity_id):
    if not isinstance(payload, dict):
        return None
    for key in ("response", "service_response"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            payload = nested
            break
    if isinstance(payload.get("forecast"), list):
        return payload["forecast"]
    entity_payload = payload.get(entity_id)
    if isinstance(entity_payload, dict) and isinstance(entity_payload.get("forecast"), list):
        return entity_payload["forecast"]
    return None


def normalize_weather(current_payload, forecast_payload, entity_id):
    if not isinstance(current_payload, dict):
        raise WeatherUnavailable("Weather data is unavailable")
    attributes = current_payload.get("attributes")
    if not isinstance(attributes, dict):
        attributes = {}
    raw_forecast = _forecast_container(forecast_payload, entity_id)
    if raw_forecast is None:
        raise WeatherUnavailable("Weather forecast is unavailable")

    forecast = []
    for item in raw_forecast:
        if len(forecast) >= 3:
            break
        if not isinstance(item, dict):
            continue
        forecast.append(
            {
                "datetime": _utc_iso(item.get("datetime")),
                "condition": _condition(item.get("condition")),
                "temperature_high": _safe_number(item.get("temperature")),
                "temperature_low": _safe_number(item.get("templow")),
                "precipitation_probability": _safe_number(item.get("precipitation_probability")),
            }
        )

    return {
        "status": "ok",
        "condition": _condition(current_payload.get("state")),
        "temperature": _safe_number(attributes.get("temperature")),
        "temperature_unit": str(attributes.get("temperature_unit") or "").strip() or None,
        "apparent_temperature": _safe_number(attributes.get("apparent_temperature")),
        "humidity": _safe_number(attributes.get("humidity")),
        "wind_speed": _safe_number(attributes.get("wind_speed")),
        "wind_speed_unit": str(attributes.get("wind_speed_unit") or "").strip() or None,
        "forecast": forecast,
        "updated_at": _utc_iso(current_payload.get("last_updated"), use_now=True),
        "stale": False,
    }


class HomeAssistantWeatherClient:
    def __init__(self, settings: WeatherSettings, client_factory: Callable = httpx.Client):
        self.settings = settings
        self.client_factory = client_factory

    def fetch(self):
        headers = {
            "Authorization": f"Bearer {self.settings.access_value}",
            "Content-Type": "application/json",
        }
        try:
            with self.client_factory(
                headers=headers,
                timeout=self.settings.timeout_seconds,
            ) as client:
                current_response = client.get(
                    f"{self.settings.base_url}/api/states/{self.settings.entity_id}"
                )
                if not current_response.is_success:
                    raise WeatherUnavailable("Home Assistant weather is unavailable")
                forecast_response = client.post(
                    f"{self.settings.base_url}/api/services/weather/get_forecasts?return_response",
                    json={"entity_id": self.settings.entity_id, "type": "daily"},
                )
                if not forecast_response.is_success:
                    raise WeatherUnavailable("Home Assistant weather is unavailable")
            try:
                current_payload = current_response.json()
                forecast_payload = forecast_response.json()
            except (ValueError, TypeError) as exc:
                raise WeatherUnavailable("Home Assistant weather is unavailable") from exc
            return normalize_weather(current_payload, forecast_payload, self.settings.entity_id)
        except httpx.HTTPError as exc:
            raise WeatherUnavailable("Home Assistant weather is unavailable") from exc


class WeatherService:
    def __init__(
        self,
        settings_loader: Callable = load_weather_settings,
        client_factory: Callable = httpx.Client,
        monotonic: Callable = time.monotonic,
    ):
        self.settings_loader = settings_loader
        self.client_factory = client_factory
        self.monotonic = monotonic
        self._lock = threading.Lock()
        self._cached = None
        self._cached_at = None

    def clear_cache(self):
        with self._lock:
            self._cached = None
            self._cached_at = None

    def get_weather(self):
        try:
            settings = self.settings_loader()
        except WeatherConfigurationError:
            return _status("unavailable")
        if settings is None:
            return _status("not_configured")

        now = self.monotonic()
        with self._lock:
            if self._cached is not None and self._cached_at is not None:
                age = max(0.0, now - self._cached_at)
                if age < settings.cache_seconds:
                    return copy.deepcopy(self._cached)
            try:
                result = HomeAssistantWeatherClient(settings, self.client_factory).fetch()
            except WeatherUnavailable:
                if self._cached is not None and self._cached_at is not None:
                    age = max(0.0, now - self._cached_at)
                    if age < settings.stale_seconds:
                        stale_result = copy.deepcopy(self._cached)
                        stale_result["status"] = "stale"
                        stale_result["stale"] = True
                        return stale_result
                return _status("unavailable")
            self._cached = copy.deepcopy(result)
            self._cached_at = now
            return copy.deepcopy(result)


def _status(status):
    return {
        "status": status,
        "condition": None,
        "temperature": None,
        "temperature_unit": None,
        "apparent_temperature": None,
        "humidity": None,
        "wind_speed": None,
        "wind_speed_unit": None,
        "forecast": [],
        "updated_at": None,
        "stale": False,
    }


weather_service = WeatherService()
router = APIRouter()


@router.get("/api/family/weather")
def family_weather():
    return weather_service.get_weather()
