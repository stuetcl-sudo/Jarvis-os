"""Non-secret onboarding status for the fixed managed Home Assistant instance."""

import os

from urllib.parse import urljoin, urlsplit

import httpx

from app import home_assistant_setup, managed_home_assistant_installer, settings_store


BACKEND_PROBE_URL = managed_home_assistant_installer.BACKEND_URL
PUBLIC_URL_ENV = "MANAGED_HOME_ASSISTANT_PUBLIC_URL"
PROBE_TIMEOUT_SECONDS = 2
TRANSITIONAL_STATES = frozenset({"installation_requested", "installing", "starting"})
PUBLIC_MESSAGES = {
    "installation_requested": "Installationen er anmodet og afventer engangs-installeren.",
    "installing": "Home Assistant installeres sikkert. Vent et øjeblik.",
    "starting": "Home Assistant er installeret og er ved at starte.",
    "onboarding_required": "Home Assistant er klar til at oprette den første konto.",
    "token_required": "Home Assistant er klar. Jarvis mangler et langtidsadgangstoken.",
    "connected": "Jarvis er sikkert forbundet til Home Assistant.",
    "failed": "Den administrerede Home Assistant-installation kræver opmærksomhed.",
}


class ManagedPublicUrlError(ValueError):
    pass


def _public_url():
    configured = os.getenv(PUBLIC_URL_ENV, "").strip()
    if not configured:
        return None, "Home Assistant-adressen til browseren skal konfigureres på serveren."
    try:
        normalized = home_assistant_setup.normalize_base_url(configured)
    except home_assistant_setup.HomeAssistantSetupError:
        raise ManagedPublicUrlError("managed_public_url_invalid") from None
    private_identifiers = (
        managed_home_assistant_installer.CONTAINER_NAME,
        managed_home_assistant_installer.NETWORK_NAME,
        "docker.sock",
    )
    if any(identifier in normalized.lower() for identifier in private_identifiers):
        raise ManagedPublicUrlError("managed_public_url_invalid")
    return normalized, ""


def _result(state, code=None, token_configured=False, public_url=None, public_url_message=""):
    return {
        "state": state,
        "code": code or state,
        "message": PUBLIC_MESSAGES[state],
        "home_assistant_url": public_url,
        "public_url_configured": bool(public_url),
        "public_url_message": public_url_message,
        "token_configured": bool(token_configured),
        "transitional": state in TRANSITIONAL_STATES,
    }


def _redirect_is_external(response):
    if not response.is_redirect:
        return False
    location = response.headers.get("location", "")
    if not location:
        return False
    expected = urlsplit(BACKEND_PROBE_URL)
    target = urlsplit(urljoin(BACKEND_PROBE_URL, location))
    return (target.scheme, target.hostname, target.port) != (
        expected.scheme,
        expected.hostname,
        expected.port,
    )


def _onboarding_required(response):
    if response.status_code != 200:
        return False
    try:
        payload = response.json()
    except ValueError:
        text = response.text.lower()
        return "onboarding" in text or "create account" in text
    steps = payload if isinstance(payload, list) else payload.get("data", []) if isinstance(payload, dict) else []
    return any(isinstance(step, dict) and step.get("done") is False for step in steps)


def _stored_token(db_path=None):
    if not settings_store.has_secret("home_assistant.token", db_path=db_path):
        return None
    return settings_store.get_secret("home_assistant.token", db_path=db_path)


def managed_onboarding_status(db_path=None, transport=None):
    install = managed_home_assistant_installer.managed_install_status(db_path=db_path)
    install_state = install["state"]
    if install_state == managed_home_assistant_installer.FAILED:
        return _result("failed", code=(install.get("error") or {}).get("code", "installation_failed"))
    if install_state == managed_home_assistant_installer.INSTALLING:
        return _result("installing")
    if install_state != managed_home_assistant_installer.INSTALLED:
        return _result("installation_requested")

    public_url = None
    public_url_message = ""
    try:
        public_url, public_url_message = _public_url()
        timeout = httpx.Timeout(PROBE_TIMEOUT_SECONDS, connect=PROBE_TIMEOUT_SECONDS)
        with httpx.Client(timeout=timeout, transport=transport, follow_redirects=False) as client:
            onboarding = client.get(f"{BACKEND_PROBE_URL}/api/onboarding")
            if _redirect_is_external(onboarding):
                return _result("failed", code="managed_redirect_rejected", public_url=public_url, public_url_message=public_url_message)
            if _onboarding_required(onboarding):
                return _result("onboarding_required", public_url=public_url, public_url_message=public_url_message)

            token = _stored_token(db_path=db_path)
            headers = home_assistant_setup._headers(token) if token else None
            api = client.get(f"{BACKEND_PROBE_URL}/api/", headers=headers)
            if _redirect_is_external(api):
                return _result(
                    "failed", code="managed_redirect_rejected", token_configured=bool(token), public_url=public_url, public_url_message=public_url_message
                )
            if api.status_code == 200:
                try:
                    payload = api.json()
                except ValueError:
                    payload = None
                if isinstance(payload, dict) and payload.get("message") == "API running.":
                    return _result(
                        "connected" if token else "token_required",
                        token_configured=bool(token),
                        public_url=public_url,
                        public_url_message=public_url_message,
                    )
            if api.status_code in {401, 403}:
                return _result(
                    "token_required",
                    code="managed_token_invalid" if token else "token_required",
                    token_configured=bool(token),
                    public_url=public_url,
                    public_url_message=public_url_message,
                )
            return _result("starting", public_url=public_url, public_url_message=public_url_message)
    except (httpx.TimeoutException, httpx.RequestError):
        return _result("starting", public_url=public_url, public_url_message=public_url_message)
    except ManagedPublicUrlError:
        return _result(
            "failed",
            code="managed_public_url_invalid",
            public_url_message="Home Assistant-adressen til browseren er ugyldig i serverkonfigurationen.",
        )
    except (OSError, RuntimeError, ValueError):
        return _result("failed", code="managed_status_unavailable")
