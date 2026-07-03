from urllib.parse import urlparse

import httpx

from app import settings_store


ALLOWED_SCHEMES = {"http", "https"}


def normalize_base_url(value):
    url = (value or "").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.netloc:
        raise ValueError("Home Assistant-adressen skal begynde med http:// eller https://")
    if parsed.username or parsed.password:
        raise ValueError("Home Assistant-adressen må ikke indeholde brugernavn eller adgangskode")
    return url


def _headers(token):
    value = (token or "").strip()
    if not value:
        raise ValueError("Home Assistant-token mangler")
    return {"Authorization": f"Bearer {value}", "Content-Type": "application/json"}


def test_connection(base_url, token, timeout_seconds=5, transport=None):
    url = normalize_base_url(base_url)
    try:
        with httpx.Client(timeout=timeout_seconds, transport=transport) as client:
            response = client.get(f"{url}/api/", headers=_headers(token))
    except httpx.TimeoutException as exc:
        raise RuntimeError("Home Assistant svarede ikke inden for tidsgrænsen") from exc
    except httpx.RequestError as exc:
        raise RuntimeError("Jarvis kunne ikke oprette forbindelse til Home Assistant") from exc
    if response.status_code in {401, 403}:
        raise RuntimeError("Home Assistant afviste tokenet")
    if response.status_code != 200:
        raise RuntimeError(f"Home Assistant svarede med HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Home Assistant returnerede et ugyldigt svar") from exc
    return {"connected": True, "message": payload.get("message", "API running.")}


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
        entities.append(
            dict(
                entity_id=entity_id,
                domain=domain,
                name=str(attributes.get("friendly_name") or entity_id),
                unit=attributes.get("unit_of_measurement"),
                device_class=attributes.get("device_class"),
                state=state.get("state"),
            )
        )
    entities.sort(key=lambda item: (item["domain"], item["name"].lower(), item["entity_id"]))
    return entities


def save_connection(base_url, token, db_path=None):
    url = normalize_base_url(base_url)
    _headers(token)
    settings_store.set_setting("home_assistant.base_url", url, db_path=db_path)
    settings_store.set_secret("home_assistant.token", token.strip(), db_path=db_path)
    return settings_store.public_connection_summary(db_path=db_path)
