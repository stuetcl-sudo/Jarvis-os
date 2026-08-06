"""Safe, owner-facing status summaries for the supported integrations."""

import os
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit, urlunsplit

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
TECHNICAL_KEYS = frozenset({"check", "configured", "warning_count", "response_class"})
ALLOWED_RESPONSE_CLASSES = frozenset({
    "success",
    "authentication",
    "not_found",
    "rate_limited",
    "server",
    "redirect",
    "response",
    "transport",
    "upstream",
    "state",
})

GUIDANCE = {
    ("home_assistant", "not_configured", None): ("Opsæt Home Assistant", "Tilføj forbindelsen under opsætning."),
    ("home_assistant", "degraded", "authentication"): ("Kontrollér login", "Forbindelsen er gemt, men loginoplysningerne skal kontrolleres."),
    ("home_assistant", "degraded", None): ("Kontrollér opsætningen", "Kontrollér den gemte Home Assistant-opsætning."),
    ("home_assistant", "unavailable", None): ("Kontrollér forbindelsen", "Kontrollér at Home Assistant kører og kan nås fra Jarvis."),
    ("scrypted", "not_configured", None): ("Opsæt Scrypted", "Tilføj Scrypted-forbindelsen under opsætning."),
    ("scrypted", "degraded", "authentication"): ("Kontrollér login", "Forbindelsen er gemt, men loginoplysningerne skal kontrolleres."),
    ("scrypted", "degraded", None): ("Kontrollér opsætningen", "Kontrollér den gemte Scrypted-opsætning."),
    ("scrypted", "unavailable", None): ("Kontrollér Scrypted", "Kontrollér at Scrypted kører og kan nås fra Jarvis."),
    ("electricity_prices", "not_configured", None): ("Vælg strømprissensor", "Vælg den sensor, der leverer strømpriser."),
    ("electricity_prices", "degraded", None): ("Kontrollér sensoren", "Kontrollér at den valgte strømprissensor leverer en gyldig værdi."),
    ("electricity_prices", "unavailable", None): ("Kontrollér Home Assistant", "Kontrollér Home Assistant-forbindelsen, før strømpriser kontrolleres igen."),
    ("jarvis", "degraded", None): ("Se systemstatus", "Se systemstatus for flere sikre oplysninger."),
}


def _item(key, name, state, summary, checked_at, technical_detail=None):
    detail = {
        field: value for field, value in (technical_detail or {}).items()
        if field in TECHNICAL_KEYS and isinstance(value, (str, int, bool))
    }
    if detail.get("response_class") not in ALLOWED_RESPONSE_CLASSES:
        detail.pop("response_class", None)
    safe_state = state if state in ALLOWED_STATES else "unavailable"
    response_class = detail.get("response_class")
    guidance = GUIDANCE.get((key, safe_state, response_class)) or GUIDANCE.get((key, safe_state, None))
    item = {
        "key": key,
        "display_name": name,
        "state": safe_state,
        "summary": summary,
        "last_checked": checked_at,
        "technical_detail": detail or None,
    }
    if guidance:
        item["action_label"], item["action_hint"] = guidance
    return item


def _home_assistant(checked_at):
    try:
        connection = load_home_assistant_connection()
        if connection is None:
            return _item("home_assistant", "Home Assistant", "not_configured", "Home Assistant er ikke konfigureret", checked_at, {"configured": False})
        payload = HomeAssistantClient(connection).get_json("/api/")
        if not isinstance(payload, dict) or payload.get("message") != "API running.":
            raise HomeAssistantUnavailable(response_class="response")
        return _item("home_assistant", "Home Assistant", "connected", "Home Assistant er forbundet", checked_at, {"configured": True, "check": "api"})
    except HomeAssistantConfigurationError:
        return _item("home_assistant", "Home Assistant", "degraded", "Home Assistant-konfigurationen kræver opmærksomhed", checked_at, {"configured": True, "check": "configuration"})
    except HomeAssistantUnavailable as exc:
        if exc.response_class == "authentication":
            return _item("home_assistant", "Home Assistant", "degraded", "Home Assistant-login kræver opmærksomhed", checked_at, {"configured": True, "check": "api", "response_class": "authentication"})
        return _item("home_assistant", "Home Assistant", "unavailable", "Home Assistant svarer ikke", checked_at, {"configured": True, "check": "api", "response_class": "transport" if exc.response_class == "transport" else "response"})
    except (OSError, RuntimeError, ValueError):
        return _item("home_assistant", "Home Assistant", "unavailable", "Home Assistant svarer ikke", checked_at, {"configured": True, "check": "api", "response_class": "transport"})


def _scrypted(checked_at):
    raw_url = os.getenv("SCRYPTED_URL", "").strip()
    if not raw_url:
        return _item("scrypted", "Scrypted", "not_configured", "Scrypted er ikke konfigureret", checked_at, {"configured": False})
    try:
        parsed = urlsplit(raw_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("invalid configuration")
        base_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
        probe_url = f"{base_url}/"
        with httpx.Client(timeout=2, follow_redirects=False) as client:
            response = client.get(probe_url)
        if 200 <= response.status_code <= 299:
            return _item("scrypted", "Scrypted", "connected", "Scrypted er forbundet", checked_at, {"configured": True, "check": "http", "response_class": "success"})
        if response.status_code in {401, 403}:
            return _item("scrypted", "Scrypted", "degraded", "Scrypted-login kræver opmærksomhed", checked_at, {"configured": True, "check": "http", "response_class": "authentication"})
        if response.status_code == 404:
            return _item("scrypted", "Scrypted", "degraded", "Scrypted-forbindelsen kræver opsætning", checked_at, {"configured": True, "check": "http", "response_class": "not_found"})
        if response.status_code == 429:
            return _item("scrypted", "Scrypted", "degraded", "Scrypted svarer med en midlertidig begrænsning", checked_at, {"configured": True, "check": "http", "response_class": "rate_limited"})
        if 500 <= response.status_code <= 599:
            return _item("scrypted", "Scrypted", "unavailable", "Scrypted svarer ikke", checked_at, {"configured": True, "check": "http", "response_class": "server"})
        return _item("scrypted", "Scrypted", "degraded", "Scrypted-forbindelsen kræver opsætning", checked_at, {"configured": True, "check": "http", "response_class": "redirect" if response.is_redirect else "response"})
    except (httpx.HTTPError, OSError, RuntimeError):
        return _item("scrypted", "Scrypted", "unavailable", "Scrypted svarer ikke", checked_at, {"configured": True, "check": "http", "response_class": "transport"})
    except ValueError:
        return _item("scrypted", "Scrypted", "degraded", "Scrypted-konfigurationen kræver opmærksomhed", checked_at, {"configured": True, "check": "configuration"})


def _electricity_prices(checked_at, home_assistant):
    try:
        entity = home_entity_settings.load_entity_settings(db_path=config.DB_PATH).get("electricity_price_entity", "")
    except (OSError, RuntimeError, ValueError):
        return _item("electricity_prices", "Strømpriser", "degraded", "Strømpriser kunne ikke kontrolleres", checked_at, {"configured": False, "check": "entity"})
    if not entity:
        return _item("electricity_prices", "Strømpriser", "not_configured", "Strømpriser er ikke konfigureret", checked_at, {"configured": False})
    if home_assistant["state"] != "connected":
        return _item("electricity_prices", "Strømpriser", "unavailable", "Strømpriser er midlertidigt utilgængelige", checked_at, {"configured": True, "check": "entity", "response_class": "upstream"})
    try:
        connection = load_home_assistant_connection()
        if connection is None:
            raise HomeAssistantUnavailable(response_class="transport")
        payload = HomeAssistantClient(connection).get_json(f"/api/states/{quote(entity, safe='')}")
        state = str(payload.get("state") if isinstance(payload, dict) else "").strip().lower()
        if state in {"", "unknown", "unavailable"}:
            return _item("electricity_prices", "Strømpriser", "degraded", "Strømpriser kræver opmærksomhed", checked_at, {"configured": True, "check": "entity", "response_class": "state"})
        return _item("electricity_prices", "Strømpriser", "healthy", "Strømpriser er klar", checked_at, {"configured": True, "check": "entity", "response_class": "success"})
    except HomeAssistantUnavailable as exc:
        if exc.response_class == "transport":
            return _item("electricity_prices", "Strømpriser", "unavailable", "Strømpriser er midlertidigt utilgængelige", checked_at, {"configured": True, "check": "entity", "response_class": "transport"})
        return _item("electricity_prices", "Strømpriser", "degraded", "Strømpriser kræver opmærksomhed", checked_at, {"configured": True, "check": "entity", "response_class": "not_found" if exc.response_class == "not_found" else "response"})
    except (OSError, RuntimeError, ValueError, TypeError):
        return _item("electricity_prices", "Strømpriser", "degraded", "Strømpriser kunne ikke kontrolleres", checked_at, {"configured": True, "check": "entity", "response_class": "response"})


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
