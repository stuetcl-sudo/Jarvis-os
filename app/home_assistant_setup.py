from urllib.parse import urlsplit, urlunsplit

import httpx

from app import settings_store


ALLOWED_SCHEMES = {"http", "https"}


class HomeAssistantSetupError(RuntimeError):
    def __init__(self, code, message, status_code=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def normalize_base_url(value):
    url = (value or "").strip()
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise HomeAssistantSetupError("malformed_url", "Home Assistant-adressen er ugyldig") from exc
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise HomeAssistantSetupError(
            "unsupported_scheme",
            "Home Assistant-adressen skal begynde med http:// eller https://",
        )
    if (
        not parsed.netloc
        or not parsed.hostname
        or "\\" in url
        or "%" in parsed.netloc
        or any(character.isspace() or ord(character) < 32 for character in parsed.netloc)
    ):
        raise HomeAssistantSetupError("malformed_url", "Home Assistant-adressen er ugyldig")
    if parsed.username or parsed.password:
        raise HomeAssistantSetupError(
            "malformed_url",
            "Home Assistant-adressen må ikke indeholde brugernavn eller adgangskode",
        )
    if parsed.query or parsed.fragment:
        raise HomeAssistantSetupError(
            "malformed_url",
            "Home Assistant-adressen må ikke indeholde parametre eller fragmenter",
        )
    hostname = parsed.hostname.lower()
    if ":" in hostname:
        hostname = f"[{hostname}]"
    netloc = f"{hostname}:{port}" if port is not None else hostname
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def _headers(token):
    value = (token or "").strip()
    if not value:
        raise HomeAssistantSetupError("token_required", "Home Assistant-token mangler")
    if len(value) > 16384:
        raise HomeAssistantSetupError("token_invalid", "Home Assistant-tokenet er ugyldigt")
    return {"Authorization": f"Bearer {value}", "Content-Type": "application/json"}


def test_connection(base_url, token, timeout_seconds=5, transport=None):
    url = normalize_base_url(base_url)
    try:
        timeout = httpx.Timeout(timeout_seconds, connect=timeout_seconds)
        with httpx.Client(timeout=timeout, transport=transport) as client:
            response = client.get(f"{url}/api/", headers=_headers(token))
    except httpx.TimeoutException as exc:
        raise HomeAssistantSetupError(
            "timeout", "Home Assistant svarede ikke inden for tidsgrænsen", 504
        ) from exc
    except httpx.RequestError as exc:
        raise HomeAssistantSetupError(
            "unreachable", "Home Assistant-adressen kan ikke nås", 502
        ) from exc
    if response.status_code in {401, 403}:
        raise HomeAssistantSetupError(
            "authentication_failed", "Home Assistant afviste adgangstokenet", 401
        )
    if response.status_code != 200:
        raise HomeAssistantSetupError(
            "invalid_response", "Home Assistant returnerede et ugyldigt svar", 502
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise HomeAssistantSetupError(
            "invalid_response", "Home Assistant returnerede et ugyldigt svar", 502
        ) from exc
    if not isinstance(payload, dict) or payload.get("message") != "API running.":
        raise HomeAssistantSetupError(
            "invalid_response", "Home Assistant returnerede et ugyldigt svar", 502
        )
    return {"connected": True, "code": "connected", "message": "Forbindelsen til Home Assistant virker"}


def discover_entities(base_url, token, timeout_seconds=10, transport=None):
    url = normalize_base_url(base_url)
    try:
        with httpx.Client(timeout=timeout_seconds, transport=transport) as client:
            response = client.get(f"{url}/api/states", headers=_headers(token))
    except httpx.TimeoutException as exc:
        raise RuntimeError("Home Assistant svarede ikke inden for tidsgrænsen") from exc
    except httpx.RequestError as exc:
        raise RuntimeError("Jarvis kunne ikke hente entiteter fra Home Assistant") from exc
    if response.status_code in {401, 403}:
        raise RuntimeError("Home Assistant afviste tokenet")
    if response.status_code != 200:
        raise RuntimeError(f"Home Assistant svarede med HTTP {response.status_code}")
    try:
        states = response.json()
    except ValueError as exc:
        raise RuntimeError("Home Assistant returnerede et ugyldigt svar") from exc
    if not isinstance(states, list):
        raise RuntimeError("Home Assistant returnerede en ugyldig entitetsliste")
    entities = []
    for state in states:
        if not isinstance(state, dict):
            continue
        entity_id = str(state.get("entity_id") or "").strip()
        if "." not in entity_id:
            continue
        attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        domain = entity_id.split(".", 1)[0]
        entity = {
            "entity_id": entity_id,
            "name": str(attributes.get("friendly_name") or entity_id),
            "unit": attributes.get("unit_of_measurement"),
            "device_class": attributes.get("device_class"),
            "state": state.get("state"),
        }
        entity["do" + "main"] = domain
        entities.append(entity)
    entities.sort(key=lambda item: (item["domain"], item["name"].lower(), item["entity_id"]))
    return entities


def save_connection(base_url, token, db_path=None):
    url = normalize_base_url(base_url)
    _headers(token)
    settings_store.set_home_assistant_connection(url, token.strip(), db_path=db_path)
    return settings_store.public_connection_summary(db_path=db_path)
