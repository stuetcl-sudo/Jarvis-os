from app.home_assistant import HomeAssistantConnection
from app.safety_status import (
    HomeAssistantSafetyStatusClient,
    SafetyStatusService,
    normalize_safety_status,
    unavailable_status,
)


def payload(entity_id, state, name=None, unit=None):
    attributes = {"friendly_name": name or entity_id}
    if unit is not None:
        attributes["unit_of_measurement"] = unit
    return {
        "entity_id": entity_id,
        "state": state,
        "attributes": attributes,
    }


def settings():
    return {
        "connection": HomeAssistantConnection("http://home-assistant.local", "test-token", 5),
        "internet": "sensor.gateway_state",
        "doors": ["binary_sensor.back_door"],
        "motion": ["binary_sensor.hall_motion"],
        "cameras": ["camera.driveway", "camera.garden"],
        "temperature": ["sensor.living_temperature", "sensor.hall_temperature"],
        "humidity": ["sensor.living_humidity", "sensor.hall_humidity"],
        "electricity_price": "sensor.electricity_price",
    }


def all_clear_states():
    return {
        "sensor.gateway_state": payload("sensor.gateway_state", "Connected", "Gateway"),
        "binary_sensor.back_door": payload("binary_sensor.back_door", "off", "Bagdør"),
        "binary_sensor.hall_motion": payload("binary_sensor.hall_motion", "off", "Gang"),
        "camera.driveway": payload("camera.driveway", "idle", "Indkørsel"),
        "camera.garden": payload("camera.garden", "streaming", "Have"),
        "sensor.living_temperature": payload("sensor.living_temperature", "20", unit="°C"),
        "sensor.hall_temperature": payload("sensor.hall_temperature", "22", unit="°C"),
        "sensor.living_humidity": payload("sensor.living_humidity", "40", unit="%"),
        "sensor.hall_humidity": payload("sensor.hall_humidity", "50", unit="%"),
        "sensor.electricity_price": payload("sensor.electricity_price", "1.234", unit="kr/kWh"),
    }


def test_all_clear_and_metrics_are_plain_language():
    result = normalize_safety_status(settings(), all_clear_states())
    assert result["internet"] == {"status": "ok", "label": "Online"}
    assert result["doors"] == {"status": "ok", "label": "Lukket"}
    assert result["motion"] == {"status": "ok", "label": "Roligt"}
    assert result["cameras"] == {"status": "ok", "label": "OK"}
    assert result["temperature"] == {"status": "ok", "label": "21°C"}
    assert result["humidity"] == {"status": "ok", "label": "45%"}
    assert result["electricity_price"] == {"status": "ok", "label": "1.23 kr/kWh"}


def test_open_door_motion_camera_and_internet_problem_are_plain_language():
    states = all_clear_states()
    states["sensor.gateway_state"] = payload("sensor.gateway_state", "Disconnected", "Gateway")
    states["binary_sensor.back_door"] = payload("binary_sensor.back_door", "on", "Bagdør")
    states["binary_sensor.hall_motion"] = payload("binary_sensor.hall_motion", "on", "Gang")
    states["camera.driveway"] = payload("camera.driveway", "unavailable", "Indkørsel")
    result = normalize_safety_status(settings(), states)
    assert result["internet"] == {"status": "warning", "label": "Ikke online"}
    assert result["doors"] == {"status": "warning", "label": "Bagdør åben"}
    assert result["motion"] == {"status": "warning", "label": "Bevægelse"}
    assert result["cameras"] == {"status": "warning", "label": "1 offline"}


def test_unconfigured_categories_are_unknown_not_errors():
    empty_settings = {
        "internet": "",
        "doors": [],
        "motion": [],
        "cameras": [],
        "temperature": [],
        "humidity": [],
        "electricity_price": "",
    }
    result = normalize_safety_status(empty_settings, {})
    for key in ["internet", "doors", "motion", "cameras", "temperature", "humidity", "electricity_price"]:
        assert result[key] == {"status": "unknown", "label": "Ikke valgt"}


def test_unavailable_status_keeps_family_safe_shape():
    result = unavailable_status("Home Assistant svarer ikke")
    assert set(result) == {
        "status",
        "internet",
        "doors",
        "motion",
        "cameras",
        "temperature",
        "humidity",
        "electricity_price",
    }
    for key in ["internet", "doors", "motion", "cameras", "temperature", "humidity", "electricity_price"]:
        assert result[key] == {"status": "unknown", "label": "Home Assistant svarer ikke"}


class FakeResponse:
    is_success = True

    def json(self):
        return list(FakeHttpClient.payload)


class FakeHttpClient:
    payload = []
    requests = []

    def __init__(self, headers=None, timeout=None):
        self.headers = headers
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def request(self, method, url, params=None, json=None):
        self.__class__.requests.append({"method": method, "url": url, "params": params, "json": json})
        return FakeResponse()


def reset_fake_client():
    FakeHttpClient.payload = list(all_clear_states().values())
    FakeHttpClient.requests = []


def test_safety_client_fetches_all_home_assistant_states_once():
    reset_fake_client()
    result = HomeAssistantSafetyStatusClient(settings(), FakeHttpClient).fetch()
    assert result["internet"]["status"] == "ok"
    assert len(FakeHttpClient.requests) == 1
    assert FakeHttpClient.requests[0]["method"] == "GET"
    assert FakeHttpClient.requests[0]["url"] == "http://home-assistant.local/api/states"


def test_safety_service_reuses_short_cache():
    reset_fake_client()
    now = [100.0]
    service = SafetyStatusService(
        settings_loader=lambda db_path=None: settings(),
        client_factory=FakeHttpClient,
        cache_seconds=10,
        clock=lambda: now[0],
    )
    first = service.get_safety_status()
    second = service.get_safety_status()
    assert first == second
    assert len(FakeHttpClient.requests) == 1

    now[0] += 11
    service.get_safety_status()
    assert len(FakeHttpClient.requests) == 2


def test():
    test_all_clear_and_metrics_are_plain_language()
    test_open_door_motion_camera_and_internet_problem_are_plain_language()
    test_unconfigured_categories_are_unknown_not_errors()
    test_unavailable_status_keeps_family_safe_shape()
    test_safety_client_fetches_all_home_assistant_states_once()
    test_safety_service_reuses_short_cache()
    print("Safety status tests OK")


if __name__ == "__main__":
    test()
