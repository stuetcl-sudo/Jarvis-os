"""Safe, owner-facing status summaries for the supported integrations."""

import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from app import config, home_entity_settings
from app.health import get_health
from app.home_assistant import (
    HomeAssistantClient,
    HomeAssistantConfigurationError,
    HomeAssistantUnavailable,
    load_home_assistant_connection,
)


ALLOWED_STATES = frozenset({"connected", "unavailable", "not_configured", "degraded", "healthy"})
TECHNICAL_KEYS = frozenset({"check", "configured", "warning_count"})


def _item(key, name, state, summary, checked_at, technical_detail=None):
    detail = {
        field: value for field, value in (technical_detail or {}).items()
        if field in TECHNICAL_KEYS and isinstance(value, (str, int, bool))
    }
    return {
        "key": key,
        "display_name": name,
        "state": state if state in ALLOWED_STATES else "unavailable",
        "summary": summary,
        "last_checked": checked_at,
        "technical_detail": detail or None,
    }


def _home_assistant(checked_at):
    try:
        connection = load_home_assistant_connection()
        if connection is None:
            return _item("home_assistant", "Home Assistant", "not_configured", "Home Assistant er ikke konfigureret", checked_at, {"configured": False})
        HomeAssistantClient(connection).get_json("/api/")
        return _item("home_assistant", "Home Assistant", "connected", "Home Assistant er forbundet", checked_at, {"configured": True, "check": "api"})
    except HomeAssistantConfigurationError:
        return _item("home_assistant", "Home Assistant", "degraded", "Home Assistant-konfigurationen kræver opmærksomhed", checked_at, {"configured": True, "check": "configuration"})
    except (HomeAssistantUnavailable, OSError, RuntimeError, ValueError):
        return _item("home_assistant", "Home Assistant", "unavailable", "Home Assistant svarer ikke", checked_at, {"configured": True, "check": "api"})


def _scrypted(checked_at):
    raw_url = os.getenv("SCRYPTED_URL", "").strip()
    if not raw_url:
        return _item("scrypted", "Scrypted", "not_configured", "Scrypted er ikke konfigureret", checked_at, {"configured": False})
    try:
        parsed = urlsplit(raw_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("invalid configuration")
        with httpx.Client(timeout=2, follow_redirects=False) as client:
            response = client.get(raw_url)
        if response.status_code >= 500:
            raise RuntimeError("unavailable")
        return _item("scrypted", "Scrypted", "connected", "Scrypted er forbundet", checked_at, {"configured": True, "check": "http"})
    except (httpx.HTTPError, OSError, RuntimeError):
        return _item("scrypted", "Scrypted", "unavailable", "Scrypted svarer ikke", checked_at, {"configured": True, "check": "http"})
    except ValueError:
        return _item("scrypted", "Scrypted", "degraded", "Scrypted-konfigurationen kræver opmærksomhed", checked_at, {"configured": True, "check": "configuration"})


def _electricity_prices(checked_at, home_assistant):
    try:
        entity = home_entity_settings.load_entity_settings(db_path=config.DB_PATH).get("electricity_price_entity", "")
    except (OSError, RuntimeError, ValueError):
        return _item("electricity_prices", "Strømpriser", "degraded", "Strømpriser kunne ikke kontrolleres", checked_at, {"configured": False, "check": "entity"})
    if not entity:
        return _item("electricity_prices", "Strømpriser", "not_configured", "Strømpriser er ikke konfigureret", checked_at, {"configured": False})
    if home_assistant["state"] == "connected":
        return _item("electricity_prices", "Strømpriser", "healthy", "Strømpriser er klar", checked_at, {"configured": True, "check": "entity"})
    return _item("electricity_prices", "Strømpriser", "unavailable", "Strømpriser er midlertidigt utilgængelige", checked_at, {"configured": True, "check": "entity"})


def _jarvis(checked_at):
    try:
        health = get_health()
        warnings = health.get("warnings") if isinstance(health, dict) else None
        warning_count = len(warnings) if isinstance(warnings, list) else 0
        if health.get("status") == "ok" and warning_count == 0:
            return _item("jarvis", "Jarvis", "healthy", "Jarvis kører normalt", checked_at, {"check": "health", "warning_count": 0})
        return _item("jarvis", "Jarvis", "degraded", "Jarvis kræver opmærksomhed", checked_at, {"check": "health", "warning_count": warning_count})
    except (OSError, RuntimeError, ValueError):
        return _item("jarvis", "Jarvis", "degraded", "Jarvis-status kunne ikke kontrolleres", checked_at, {"check": "health"})


def _safe_check(check, fallback):
    try:
        return check()
    except Exception:
        return fallback


def integration_status(now=None):
    checked_at = (now or datetime.now(timezone.utc)).isoformat()
    home_assistant = _safe_check(
        lambda: _home_assistant(checked_at),
        _item("home_assistant", "Home Assistant", "unavailable", "Home Assistant svarer ikke", checked_at, {"check": "api"}),
    )
    return {
        "checked_at": checked_at,
        "integrations": [
            home_assistant,
            _safe_check(lambda: _scrypted(checked_at), _item("scrypted", "Scrypted", "unavailable", "Scrypted svarer ikke", checked_at, {"check": "http"})),
            _safe_check(lambda: _electricity_prices(checked_at, home_assistant), _item("electricity_prices", "Strømpriser", "degraded", "Strømpriser kunne ikke kontrolleres", checked_at, {"check": "entity"})),
            _safe_check(lambda: _jarvis(checked_at), _item("jarvis", "Jarvis", "degraded", "Jarvis-status kunne ikke kontrolleres", checked_at, {"check": "health"})),
        ],
    }
