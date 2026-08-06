import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx

from app import managed_home_assistant_installer as installer
from app import managed_home_assistant_onboarding as onboarding
from app import settings_store


ROOT = Path(__file__).resolve().parents[1]


def installed_db(folder):
    db_path = os.path.join(folder, "jarvis.db")
    settings_store.set_setting(installer.STATE_SETTING, installer.INSTALLED, db_path=db_path)
    return db_path


def transport(handler):
    return httpx.MockTransport(handler)


def test_unreachable_installed_endpoint_is_starting_and_uses_fixed_url():
    with tempfile.TemporaryDirectory() as folder:
        db_path = installed_db(folder)

        def handler(request):
            assert str(request.url).startswith(onboarding.MANAGED_URL)
            assert request.url.path == "/api/onboarding"
            raise httpx.ConnectError("private diagnostic", request=request)

        result = onboarding.managed_onboarding_status(db_path, transport=transport(handler))
        assert result["state"] == "starting"
        assert result["home_assistant_url"] == installer.EXPECTED_LOCAL_URL
        assert "private diagnostic" not in repr(result)


def test_onboarding_response_requires_first_account():
    with tempfile.TemporaryDirectory() as folder:
        db_path = installed_db(folder)

        def handler(request):
            return httpx.Response(200, json=[{"step": "user", "done": False}])

        result = onboarding.managed_onboarding_status(db_path, transport=transport(handler))
        assert result["state"] == "onboarding_required"
        assert result["token_configured"] is False


def test_reachable_api_without_token_requires_token():
    with tempfile.TemporaryDirectory() as folder:
        db_path = installed_db(folder)

        def handler(request):
            if request.url.path == "/api/onboarding":
                return httpx.Response(200, json=[{"step": "user", "done": True}])
            assert request.url.path == "/api/"
            assert "Authorization" not in request.headers
            return httpx.Response(401, json={"message": "Unauthorized"})

        result = onboarding.managed_onboarding_status(db_path, transport=transport(handler))
        assert result["state"] == "token_required"
        assert "token" not in result


def test_valid_stored_token_is_connected_and_never_returned():
    with tempfile.TemporaryDirectory() as folder, patch.dict(
        os.environ, {"CONFIG_MASTER_KEY": "managed-onboarding-test-key"}
    ):
        db_path = installed_db(folder)
        token = "example-managed-secret"
        settings_store.set_secret("home_assistant.token", token, db_path=db_path)

        def handler(request):
            if request.url.path == "/api/onboarding":
                return httpx.Response(200, json=[{"step": "user", "done": True}])
            assert request.url.path == "/api/"
            assert request.headers["Authorization"] == f"Bearer {token}"
            return httpx.Response(200, json={"message": "API running."})

        result = onboarding.managed_onboarding_status(db_path, transport=transport(handler))
        assert result["state"] == "connected"
        assert result["token_configured"] is True
        assert token not in repr(result)


def test_arbitrary_redirect_host_is_rejected_without_following():
    with tempfile.TemporaryDirectory() as folder:
        db_path = installed_db(folder)
        requests = []

        def handler(request):
            requests.append(str(request.url))
            return httpx.Response(302, headers={"Location": "https://redirect.example/private"})

        result = onboarding.managed_onboarding_status(db_path, transport=transport(handler))
        assert result["state"] == "failed"
        assert result["code"] == "managed_redirect_rejected"
        assert requests == [f"{onboarding.MANAGED_URL}/api/onboarding"]
        assert "redirect.example" not in repr(result)


def test_installer_states_are_sanitized_for_onboarding():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        settings_store.set_setting(installer.STATE_SETTING, installer.INSTALLING, db_path=db_path)
        installing = onboarding.managed_onboarding_status(db_path)
        assert installing["state"] == "installing"
        serialized = repr(installing)
        for private in (installer.CONTAINER_NAME, installer.VOLUME_NAME, installer.NETWORK_NAME, "docker.sock"):
            assert private not in serialized


def test_frontend_polling_and_dom_security_contract():
    source = (ROOT / "app" / "static" / "js" / "setup.js").read_text(encoding="utf-8")
    html = (ROOT / "app" / "static" / "setup.html").read_text(encoding="utf-8")
    assert 'options.credentials = "same-origin"' in source
    assert "MANAGED_ONBOARDING_POLL_MS = 3000" in source
    assert 'new Set(["installation_requested", "installing", "starting"])' in source
    assert "if (document.hidden" in source
    assert 'document.addEventListener("visibilitychange"' in source
    assert "stopManagedOnboardingPolling()" in source
    assert 'openLink.href = status.home_assistant_url' in source
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html
    for forbidden in ("innerHTML", "insertAdjacentHTML", "eval(", "localStorage", "sessionStorage"):
        assert forbidden not in source


def test():
    test_unreachable_installed_endpoint_is_starting_and_uses_fixed_url()
    test_onboarding_response_requires_first_account()
    test_reachable_api_without_token_requires_token()
    test_valid_stored_token_is_connected_and_never_returned()
    test_arbitrary_redirect_host_is_rejected_without_following()
    test_installer_states_are_sanitized_for_onboarding()
    test_frontend_polling_and_dom_security_contract()
    print("Managed Home Assistant onboarding tests OK")


if __name__ == "__main__":
    test()
