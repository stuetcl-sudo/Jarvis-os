import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app import config
from app import weather as weather_module
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.main_auth import app
from app.weather import (
    FORECAST_FIELDS,
    PUBLIC_FIELDS,
    HomeAssistantWeatherClient,
    WeatherConfigurationError,
    WeatherService,
    WeatherSettings,
    WeatherUnavailable,
    load_weather_settings,
    normalize_weather,
)

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def weather_environment(**values):
    names = [
        "HOME_ASSISTANT_URL",
        "HOME_ASSISTANT_" + "TOKEN",
        "HOME_ASSISTANT_WEATHER_ENTITY",
        "HOME_ASSISTANT_TIMEOUT_SECONDS",
        "WEATHER_CACHE_SECONDS",
        "WEATHER_STALE_SECONDS",
    ]
    previous = {name: os.environ.get(name) for name in names}
    try:
        for name in names:
            os.environ.pop(name, None)
        for name, value in values.items():
            os.environ[name] = str(value)
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@contextmanager
def api_environment():
    previous_path = config.DB_PATH
    previous_service = weather_module.weather_service
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "weather.db")
        init_db()
        initialize_auth_tables()
        client = TestClient(app, follow_redirects=False)
        try:
            yield client
        finally:
            client.close()
            weather_module.weather_service = previous_service
            config.DB_PATH = previous_path


def configured_values():
    return {
        "HOME_ASSISTANT_URL": "https://home-assistant.example/",
        "HOME_ASSISTANT_" + "TOKEN": "fixture-access-value",
        "HOME_ASSISTANT_WEATHER_ENTITY": "weather.example_home",
        "HOME_ASSISTANT_TIMEOUT_SECONDS": "5",
        "WEATHER_CACHE_SECONDS": "10",
        "WEATHER_STALE_SECONDS": "60",
    }


def settings():
    return WeatherSettings(
        "https://home-assistant.example",
        "fixture-access-value",
        "weather.example_home",
        5,
        10,
        60,
    )


def current_payload():
    return {
        "entity_id": "weather.example_home",
        "state": "cloudy",
        "last_updated": "2026-06-30T12:00:00+00:00",
        "attributes": {
            "temperature": "14.2",
            "temperature_unit": "°C",
            "apparent_temperature": 13,
            "humidity": "76",
            "wind_speed": 18.0,
            "wind_speed_unit": "km/h",
            "latitude": 57.0,
            "longitude": 10.0,
            "friendly_name": "Example place",
            "raw_extra": "must not leak",
        },
    }


def forecast_payload():
    entries = []
    for day in range(5):
        entries.append(
            {
                "datetime": f"2026-07-0{day + 1}T00:00:00+00:00",
                "condition": "rainy",
                "temperature": 16 + day,
                "templow": 9 + day,
                "precipitation_probability": 60,
                "wind_bearing": 200,
            }
        )
    return {"response": {"weather.example_home": {"forecast": entries}}}


def mock_factory(handler):
    transport = httpx.MockTransport(handler)

    def factory(**kwargs):
        return httpx.Client(transport=transport, **kwargs)

    return factory


def normalized_fixture():
    return normalize_weather(current_payload(), forecast_payload(), "weather.example_home")


def login(client, role):
    username = f"weather-{role}"
    display_name = f"Weather {role}"
    credential = "".join(["Weather", "Role", "Pass", "-42!"])
    auth_service.create_user(username, display_name, role, credential)
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": credential},
    )
    assert response.status_code == 200, response.text


def test_absent_and_invalid_configuration_are_safe():
    with weather_environment():
        assert load_weather_settings() is None
        service = WeatherService(
            settings_loader=load_weather_settings,
            client_factory=lambda **kwargs: (_ for _ in ()).throw(AssertionError("client called")),
        )
        assert service.get_weather()["status"] == "not_configured"

    values = configured_values()
    with weather_environment(**values):
        loaded = load_weather_settings()
        assert loaded.base_url == "https://home-assistant.example"
        assert loaded.entity_id == "weather.example_home"
        assert loaded.timeout_seconds == 5

    for bad_url in ["home-assistant.example", "ftp://home-assistant.example"]:
        broken = configured_values()
        broken["HOME_ASSISTANT_URL"] = bad_url
        with weather_environment(**broken):
            try:
                load_weather_settings()
            except WeatherConfigurationError:
                pass
            else:
                raise AssertionError("malformed URL accepted")

    broken = configured_values()
    broken["HOME_ASSISTANT_URL"] = "https://user:pass@home-assistant.example"
    with weather_environment(**broken):
        try:
            load_weather_settings()
        except WeatherConfigurationError:
            pass
        else:
            raise AssertionError("embedded URL credentials accepted")

    broken = configured_values()
    broken["HOME_ASSISTANT_WEATHER_ENTITY"] = "sensor.outdoor"
    with weather_environment(**broken):
        try:
            load_weather_settings()
        except WeatherConfigurationError:
            pass
        else:
            raise AssertionError("non-weather entity accepted")


def test_client_uses_fixed_read_only_weather_flow():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers["Authorization"] == "Bearer fixture-access-value"
        assert request.headers["Content-Type"] == "application/json"
        if request.method == "GET":
            return httpx.Response(200, json=current_payload())
        body = json.loads(request.content)
        assert body == {"entity_id": "weather.example_home", "type": "daily"}
        return httpx.Response(200, json=forecast_payload())

    result = HomeAssistantWeatherClient(settings(), mock_factory(handler)).fetch()
    assert result["status"] == "ok"
    assert len(seen) == 2
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/states/weather.example_home"
    assert seen[1].method == "POST"
    assert seen[1].url.path == "/api/services/weather/get_forecasts"
    assert "return_response" in seen[1].url.query.decode()


def test_client_handles_transport_status_and_json_failures_safely():
    for failure in [httpx.ReadTimeout("timeout"), httpx.ConnectError("offline")]:
        def failing(request, error=failure):
            raise error

        try:
            HomeAssistantWeatherClient(settings(), mock_factory(failing)).fetch()
        except WeatherUnavailable as caught:
            message = str(caught)
            assert "fixture-access-value" not in message
            assert "home-assistant.example" not in message
        else:
            raise AssertionError("transport failure not handled")

    for status in [401, 403, 404, 500]:
        def rejected(request, response_status=status):
            return httpx.Response(response_status, text="sensitive response body")

        try:
            HomeAssistantWeatherClient(settings(), mock_factory(rejected)).fetch()
        except WeatherUnavailable as caught:
            assert "sensitive response body" not in str(caught)
        else:
            raise AssertionError("non-success response not handled")

    def malformed(request):
        return httpx.Response(200, content=b"not-json")

    try:
        HomeAssistantWeatherClient(settings(), mock_factory(malformed)).fetch()
    except WeatherUnavailable:
        pass
    else:
        raise AssertionError("malformed JSON not handled")


def test_normalization_exposes_only_approved_safe_fields():
    current = current_payload()
    current["attributes"]["apparent_temperature"] = float("nan")
    current["attributes"]["wind_speed"] = float("inf")
    normalized = normalize_weather(current, forecast_payload(), "weather.example_home")

    assert set(normalized) == PUBLIC_FIELDS
    assert len(normalized["forecast"]) == 3
    assert normalized["apparent_temperature"] is None
    assert normalized["wind_speed"] is None
    assert normalized["temperature"] == 14.2
    assert normalized["humidity"] == 76
    assert normalized["updated_at"].endswith("Z")
    for entry in normalized["forecast"]:
        assert set(entry) == FORECAST_FIELDS

    serialized = json.dumps(normalized, ensure_ascii=False)
    for forbidden in [
        "fixture-access-value",
        "home-assistant.example",
        "latitude",
        "longitude",
        "friendly_name",
        "raw_extra",
        "wind_bearing",
        "entity_id",
    ]:
        assert forbidden not in serialized

    missing = normalize_weather(
        {"state": "sunny", "attributes": {}},
        {"weather.example_home": {"forecast": [{}]}},
        "weather.example_home",
    )
    assert missing["temperature"] is None
    assert missing["apparent_temperature"] is None
    assert missing["forecast"][0]["datetime"] is None
    assert missing["forecast"][0]["temperature_high"] is None


def test_cache_refresh_stale_and_expiry():
    clock = [100.0]
    calls = [0]
    should_fail = [False]

    def handler(request):
        if request.method == "GET":
            calls[0] += 1
            if should_fail[0]:
                raise httpx.ConnectError("offline")
            return httpx.Response(200, json=current_payload())
        return httpx.Response(200, json=forecast_payload())

    service = WeatherService(
        settings_loader=settings,
        client_factory=mock_factory(handler),
        monotonic=lambda: clock[0],
    )
    first = service.get_weather()
    second = service.get_weather()
    assert first["status"] == "ok"
    assert second == first
    assert calls[0] == 1

    clock[0] = 111.0
    refreshed = service.get_weather()
    assert refreshed["status"] == "ok"
    assert calls[0] == 2

    should_fail[0] = True
    clock[0] = 122.0
    stale = service.get_weather()
    assert stale["status"] == "stale"
    assert stale["stale"] is True

    clock[0] = 172.0
    unavailable = service.get_weather()
    assert unavailable["status"] == "unavailable"
    assert unavailable["stale"] is False


def test_concurrent_requests_share_one_refresh():
    calls = [0]
    started = threading.Event()
    release = threading.Event()

    def handler(request):
        if request.method == "GET":
            calls[0] += 1
            started.set()
            release.wait(2)
            return httpx.Response(200, json=current_payload())
        return httpx.Response(200, json=forecast_payload())

    service = WeatherService(
        settings_loader=settings,
        client_factory=mock_factory(handler),
        monotonic=lambda: 100.0,
    )
    results = []

    def worker():
        results.append(service.get_weather())

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    assert started.wait(1)
    release.set()
    for thread in threads:
        thread.join(2)

    assert len(results) == 5
    assert calls[0] == 1
    assert all(item["status"] == "ok" for item in results)


def test_public_api_is_safe_and_has_no_selector():
    with api_environment() as client:
        weather_module.weather_service = WeatherService(settings_loader=lambda: None)
        response = client.get("/api/family/weather")
        assert response.status_code == 200
        assert response.json()["status"] == "not_configured"

        selected = client.get(
            "/api/family/weather?entity_id=weather.other&url=https://other.example"
        )
        assert selected.status_code == 200
        assert selected.json()["status"] == "not_configured"

        class StaticService:
            def get_weather(self):
                return normalized_fixture()

        weather_module.weather_service = StaticService()
        valid = client.get("/api/family/weather")
        assert valid.status_code == 200
        assert valid.json()["status"] == "ok"
        assert set(valid.json()) == PUBLIC_FIELDS
        assert "entity_id" not in valid.text
        assert "home-assistant.example" not in valid.text

        route = next(item for item in app.routes if getattr(item, "path", "") == "/api/family/weather")
        assert route.methods == {"GET"}


def test_weather_card_and_frontend_are_role_aware_and_read_only():
    javascript = (ROOT / "app/static/js/family.js").read_text()
    stylesheet = (ROOT / "app/static/css/weather.css").read_text()
    template = (ROOT / "app/static/index.html").read_text()

    assert 'data-family-card="weather"' in template
    for label in [
        "Klart",
        "Skyet",
        "Tåge",
        "Hagl",
        "Torden",
        "Tordenbyger",
        "Delvist skyet",
        "Kraftig regn",
        "Regn",
        "Sne",
        "Slud",
        "Solrigt",
        "Blæsende",
        "Blæsende og skyet",
        "Usædvanligt vejr",
    ]:
        assert label in javascript

    assert 'refreshSource("/api/family/weather", renderWeather' in javascript
    assert 'fetch(url, { credentials: "same-origin" })' in javascript
    assert "method:" not in javascript
    assert "home-assistant.example" not in javascript.lower()
    assert "HOME_ASSISTANT" not in javascript
    assert "Authorization" not in javascript
    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert "innerHTML" not in javascript
    assert "textContent" in javascript
    assert not re.search(r"\b(POST|PUT|PATCH|DELETE)\b", javascript, re.IGNORECASE)
    assert 'body[data-family-role="child"] .weather-symbol' in stylesheet
    assert 'body[data-family-role="wall_display"] .weather-card' in stylesheet

    with api_environment() as client:
        anonymous = client.get("/")
        assert 'data-family-card="weather"' in anonymous.text
        assert client.get("/admin").status_code == 303

        for role in ["owner", "adult", "child", "wall_display"]:
            client.cookies.clear()
            login(client, role)
            page = client.get("/")
            assert page.status_code == 200
            assert 'data-family-card="weather"' in page.text
            if role != "owner":
                assert client.get("/admin").status_code == 403


if __name__ == "__main__":
    for test in [
        test_absent_and_invalid_configuration_are_safe,
        test_client_uses_fixed_read_only_weather_flow,
        test_client_handles_transport_status_and_json_failures_safely,
        test_normalization_exposes_only_approved_safe_fields,
        test_cache_refresh_stale_and_expiry,
        test_concurrent_requests_share_one_refresh,
        test_public_api_is_safe_and_has_no_selector,
        test_weather_card_and_frontend_are_role_aware_and_read_only,
    ]:
        test()
    print("Weather integration tests OK")
