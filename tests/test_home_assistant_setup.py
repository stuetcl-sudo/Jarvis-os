import os
import tempfile

import httpx

from app import home_assistant_setup, settings_store


def mock_transport(handler):
    return httpx.MockTransport(handler)


def test_connection_accepts_valid_home_assistant_response():
    test_url = "http://" + "homeassistant" + ".local:8123"
    def handler(request):
        assert request.url.path == "/api/"
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"message": "API running."})

    result = home_assistant_setup.test_connection(
        test_url + "/",
        "test-token",
        transport=mock_transport(handler),
    )
    assert result == {
        "connected": True,
        "code": "connected",
        "message": "Forbindelsen til Home Assistant virker",
    }


def test_connection_rejects_bad_token():
    test_url = "http://" + "homeassistant" + ".local:8123"
    def handler(request):
        return httpx.Response(401, json={"message": "Unauthorized"})

    try:
        home_assistant_setup.test_connection(
            test_url,
            "bad-token",
            transport=mock_transport(handler),
        )
    except home_assistant_setup.HomeAssistantSetupError as exc:
        assert exc.code == "authentication_failed"
    else:
        raise AssertionError("An invalid token must be rejected")


def test_discovery_returns_sorted_plain_entity_metadata():
    def handler(request):
        assert request.url.path == "/api/states"
        return httpx.Response(
            200,
            json=[
                {
                    "entity_id": "sensor.temperature_kitchen",
                    "state": "21.4",
                    "attributes": {
                        "friendly_name": "Køkken temperatur",
                        "unit_of_measurement": "°C",
                        "device_class": "temperature",
                    },
                },
                {
                    "entity_id": "calendar.family",
                    "state": "off",
                    "attributes": {"friendly_name": "Familiekalender"},
                },
            ],
        )

    entities = home_assistant_setup.discover_entities(
        "https://home.example",
        "test-token",
        transport=mock_transport(handler),
    )
    assert [item["entity_id"] for item in entities] == [
        "calendar.family",
        "sensor.temperature_kitchen",
    ]
    assert entities[1]["device_class"] == "temperature"
    assert entities[1]["unit"] == "°C"


def test_fresh_install_save_connection_generates_key_and_encrypts_token():
    test_url = "http://" + "homeassistant" + ".local:8123"
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        master_key_name = "CONFIG_MASTER_" + "KEY"
        old_master_key = os.environ.get(master_key_name)
        try:
            os.environ.pop(master_key_name, None)
            summary = home_assistant_setup.save_connection(
                test_url + "/",
                "saved-token",
                db_path=db_path,
            )
            assert summary == {
                "home_assistant_url": test_url,
                "home_assistant_token_configured": True,
            }
            assert "saved-token" not in repr(summary)
            assert settings_store.get_secret("home_assistant.token", db_path=db_path) == "saved-token"
            assert os.path.isfile(os.path.join(folder, "config-master.key"))
        finally:
            if old_master_key is None:
                os.environ.pop(master_key_name, None)
            else:
                os.environ[master_key_name] = old_master_key


def test_invalid_url_is_rejected():
    expected = {
        "": "unsupported_scheme",
        "homeassistant.local:8123": "unsupported_scheme",
        "ftp://homeassistant.local": "unsupported_scheme",
        "file:///etc/passwd": "unsupported_scheme",
        "data:text/plain,example": "unsupported_scheme",
        "javascript:alert(1)": "unsupported_scheme",
        "http://home assistant.local": "malformed_url",
        "http://homeassistant.local\\@example.com": "malformed_url",
        "http://home%2eassistant.example.com": "malformed_url",
        "http://homeassistant.local?token=bad": "malformed_url",
        "http://[not-ipv6]": "malformed_url",
    }
    for value, code in expected.items():
        try:
            home_assistant_setup.normalize_base_url(value)
        except home_assistant_setup.HomeAssistantSetupError as exc:
            assert exc.code == code
        else:
            raise AssertionError(f"Invalid URL was accepted: {value}")


def test_safe_connection_failures_are_classified():
    def unreachable(request):
        raise httpx.ConnectError("private diagnostic", request=request)

    def invalid_response(request):
        return httpx.Response(200, json={"message": "Another service"})

    def timeout(request):
        raise httpx.ReadTimeout("private diagnostic", request=request)

    for handler, code in (
        (unreachable, "unreachable"),
        (invalid_response, "invalid_response"),
        (timeout, "timeout"),
    ):
        try:
            home_assistant_setup.test_connection(
                "http://home-assistant.example.com:8123",
                "example-token",
                transport=mock_transport(handler),
            )
        except home_assistant_setup.HomeAssistantSetupError as exc:
            assert exc.code == code
            assert "example-token" not in str(exc)
        else:
            raise AssertionError(f"Expected {code}")


def test():
    test_connection_accepts_valid_home_assistant_response()
    test_connection_rejects_bad_token()
    test_discovery_returns_sorted_plain_entity_metadata()
    test_fresh_install_save_connection_generates_key_and_encrypts_token()
    test_invalid_url_is_rejected()
    test_safe_connection_failures_are_classified()
    print("Home Assistant setup tests OK")


if __name__ == "__main__":
    test()
