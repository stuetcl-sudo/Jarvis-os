import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app import calendar as calendar_module
from app import config
from app.auth.service import auth_service, initialize_auth_tables
from app.calendar import (
    CalendarConfigurationError,
    CalendarService,
    CalendarSettings,
    HomeAssistantCalendarClient,
    load_calendar_settings,
    normalize_event,
    parse_calendar_sources,
)
from app.db import init_db
from app.home_assistant import HomeAssistantConnection
from app.main_auth import app

ROOT = Path(__file__).resolve().parents[1]
LOCAL_TZ = timezone(timedelta(hours=2))
FIXED_NOW = datetime(2026, 7, 1, 10, 0, tzinfo=LOCAL_TZ)


@contextmanager
def environment(**values):
    names = [
        "HOME_ASSISTANT_URL",
        "HOME_ASSISTANT_" + "TOKEN",
        "HOME_ASSISTANT_CALENDARS",
        "HOME_ASSISTANT_TIMEOUT_SECONDS",
        "CALENDAR_LOOKAHEAD_DAYS",
        "CALENDAR_CACHE_SECONDS",
        "CALENDAR_STALE_SECONDS",
        "CALENDAR_MAX_EVENTS",
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
    previous_service = calendar_module.calendar_service
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "calendar.db")
        init_db()
        initialize_auth_tables()
        client = TestClient(app, follow_redirects=False)
        try:
            yield client
        finally:
            client.close()
            calendar_module.calendar_service = previous_service
            config.DB_PATH = previous_path


def mapping_value():
    return (
        "calendar.example_green|Green calendar|green,"
        "calendar.example_blue|Blue calendar|blue,"
        "calendar.example_violet|Violet calendar|violet,"
        "calendar.example_yellow|Shared calendar|yellow"
    )


def configured_values():
    return {
        "HOME_ASSISTANT_URL": "https://home-assistant.example/",
        "HOME_ASSISTANT_" + "TOKEN": "fixture-access-value",
        "HOME_ASSISTANT_CALENDARS": mapping_value(),
        "HOME_ASSISTANT_TIMEOUT_SECONDS": "5",
        "CALENDAR_LOOKAHEAD_DAYS": "7",
        "CALENDAR_CACHE_SECONDS": "10",
        "CALENDAR_STALE_SECONDS": "60",
        "CALENDAR_MAX_EVENTS": "40",
    }


def settings(max_events=40):
    return CalendarSettings(
        connection=HomeAssistantConnection(
            "https://home-assistant.example",
            "fixture-access-value",
            5,
        ),
        calendars=parse_calendar_sources(mapping_value()),
        lookahead_days=7,
        cache_seconds=10,
        stale_seconds=60,
        max_events=max_events,
    )


def timed_event(title="Tandlæge", start="2026-07-01T08:30:00+02:00"):
    start_time = datetime.fromisoformat(start)
    return {
        "summary": title,
        "start": {"dateTime": start_time.isoformat()},
        "end": {"dateTime": (start_time + timedelta(minutes=45)).isoformat()},
        "description": "private description",
        "location": "private location",
        "attendees": [{"name": "private attendee"}],
        "uid": "private uid",
    }


def all_day_event(title="Fridag"):
    return {
        "summary": title,
        "start": {"date": "2026-07-02"},
        "end": {"date": "2026-07-03"},
        "description": "private description",
    }


def mock_factory(handler):
    transport = httpx.MockTransport(handler)

    def factory(**kwargs):
        return httpx.Client(transport=transport, **kwargs)

    return factory


def login(client, role):
    username = f"calendar-{role}"
    credential = "".join(["Calendar", "Role", "Pass", "-42!"])
    auth_service.create_user(username, f"Calendar {role}", role, credential)
    response = client.post("/api/auth/login", json={"username": username, "password": credential})
    assert response.status_code == 200, response.text


def authenticated_snapshot():
    sources = parse_calendar_sources(mapping_value())
    events = [
        normalize_event(timed_event(), sources[0], FIXED_NOW, LOCAL_TZ),
        normalize_event(all_day_event(), sources[3], FIXED_NOW, LOCAL_TZ),
    ]
    return {
        "status": "ok",
        "today_count": 1,
        "upcoming_count": 2,
        "next_event_start": events[0]["start"],
        "events": events,
        "calendars": [
            {"key": source.key, "label": source.label, "color": source.color}
            for source in sources
        ],
        "unavailable_calendars": 0,
        "stale": False,
    }


def test_configuration_parsing_and_rejection():
    with environment():
        assert load_calendar_settings() is None
        assert CalendarService(settings_loader=load_calendar_settings).get_calendar()["status"] == "not_configured"

    with environment(**configured_values()):
        loaded = load_calendar_settings()
        assert len(loaded.calendars) == 4
        assert [item.color for item in loaded.calendars] == ["green", "blue", "violet", "yellow"]
        assert loaded.connection.base_url == "https://home-assistant.example"

    invalid_values = [
        "calendar.example|Missing color",
        "sensor.example|Example|green",
        "calendar.example|Example|orange",
        "calendar.example|One|green,calendar.example|Two|blue",
    ]
    for raw_value in invalid_values:
        try:
            parse_calendar_sources(raw_value)
        except CalendarConfigurationError:
            pass
        else:
            raise AssertionError("invalid mapping accepted")

    for field in [
        "CALENDAR_LOOKAHEAD_DAYS",
        "CALENDAR_CACHE_SECONDS",
        "CALENDAR_STALE_SECONDS",
        "CALENDAR_MAX_EVENTS",
    ]:
        values = configured_values()
        values[field] = "0"
        with environment(**values):
            try:
                load_calendar_settings()
            except CalendarConfigurationError:
                pass
            else:
                raise AssertionError(f"invalid integer accepted for {field}")


def test_client_uses_configured_get_endpoints_and_server_range():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer fixture-access-value"
        assert request.url.params["start"].startswith("2026-07-01T00:00:00")
        assert request.url.params["end"].startswith("2026-07-08T00:00:00")
        assert request.url.path.startswith("/api/calendars/calendar.example_")
        return httpx.Response(200, json=[timed_event()])

    events, failures, _, _ = HomeAssistantCalendarClient(settings(), mock_factory(handler)).fetch(FIXED_NOW)
    assert failures == 0
    assert len(events) == 4
    assert len(seen) == 4
    assert {request.url.path for request in seen} == {
        "/api/calendars/calendar.example_green",
        "/api/calendars/calendar.example_blue",
        "/api/calendars/calendar.example_violet",
        "/api/calendars/calendar.example_yellow",
    }


def test_client_handles_failures_and_partial_results_safely():
    def partial_handler(request):
        if request.url.path.endswith("example_blue"):
            raise httpx.ReadTimeout("timeout")
        if request.url.path.endswith("example_violet"):
            return httpx.Response(403, text="private response body")
        if request.url.path.endswith("example_yellow"):
            return httpx.Response(200, content=b"not-json")
        return httpx.Response(200, json=[timed_event()])

    events, failures, _, _ = HomeAssistantCalendarClient(settings(), mock_factory(partial_handler)).fetch(FIXED_NOW)
    assert failures == 3
    assert len(events) == 1

    def connection_failure(request):
        raise httpx.ConnectError("offline")

    _, failures, _, _ = HomeAssistantCalendarClient(settings(), mock_factory(connection_failure)).fetch(FIXED_NOW)
    assert failures == 4


def test_normalization_is_safe_and_deterministic():
    source = parse_calendar_sources(mapping_value())[0]
    timed = normalize_event(timed_event("  Tandlæge  "), source, FIXED_NOW, LOCAL_TZ)
    all_day = normalize_event(all_day_event(), source, FIXED_NOW, LOCAL_TZ)
    empty = normalize_event(timed_event("   "), source, FIXED_NOW, LOCAL_TZ)
    long_title = normalize_event(timed_event("x" * 200), source, FIXED_NOW, LOCAL_TZ)

    assert timed == {
        "calendar": {"key": "green-calendar", "label": "Green calendar", "color": "green"},
        "title": "Tandlæge",
        "start": "2026-07-01T08:30:00+02:00",
        "end": "2026-07-01T09:15:00+02:00",
        "all_day": False,
        "ongoing": False,
    }
    assert all_day["start"] == "2026-07-02"
    assert all_day["end"] == "2026-07-03"
    assert all_day["all_day"] is True
    assert empty["title"] == "Aftale"
    assert len(long_title["title"]) == 120

    malformed = timed_event()
    malformed["start"] = {"dateTime": "invalid"}
    assert normalize_event(malformed, source, FIXED_NOW, LOCAL_TZ) is None

    serialized = json.dumps([timed, all_day], ensure_ascii=False)
    for forbidden in [
        "description",
        "location",
        "attendee",
        "uid",
        "calendar.example",
        "fixture-access-value",
        "home-assistant.example",
    ]:
        assert forbidden not in serialized


def test_sorting_limit_cache_stale_and_concurrency():
    clock = [100.0]
    calls = [0]
    fail_all = [False]

    def handler(request):
        calls[0] += 1
        if fail_all[0]:
            raise httpx.ConnectError("offline")
        suffix = request.url.path.rsplit("_", 1)[-1]
        minute = {"green": 40, "blue": 20, "violet": 30, "yellow": 10}[suffix]
        return httpx.Response(200, json=[timed_event(suffix, f"2026-07-01T08:{minute:02d}:00+02:00")])

    limited_settings = settings(max_events=3)
    service = CalendarService(
        settings_loader=lambda: limited_settings,
        client_factory=mock_factory(handler),
        monotonic=lambda: clock[0],
        now_provider=lambda: FIXED_NOW,
    )
    first = service.get_calendar({"role": "owner"})
    second = service.get_calendar({"role": "owner"})
    assert [item["title"] for item in first["events"]] == ["yellow", "blue", "violet"]
    assert second == first
    assert calls[0] == 4

    clock[0] = 111.0
    assert service.get_calendar({"role": "owner"})["status"] == "ok"
    assert calls[0] == 8

    fail_all[0] = True
    clock[0] = 122.0
    stale = service.get_calendar({"role": "owner"})
    assert stale["status"] == "stale"
    assert stale["stale"] is True

    clock[0] = 172.0
    assert service.get_calendar({"role": "owner"})["status"] == "unavailable"

    release = threading.Event()
    concurrent_calls = [0]

    def concurrent_handler(request):
        concurrent_calls[0] += 1
        release.wait(2)
        return httpx.Response(200, json=[timed_event()])

    concurrent_service = CalendarService(
        settings_loader=settings,
        client_factory=mock_factory(concurrent_handler),
        monotonic=lambda: 200.0,
        now_provider=lambda: FIXED_NOW,
    )
    results = []
    threads = [threading.Thread(target=lambda: results.append(concurrent_service.get_calendar({"role": "adult"}))) for _ in range(5)]
    for thread in threads:
        thread.start()
    release.set()
    for thread in threads:
        thread.join(2)
    assert len(results) == 5
    assert concurrent_calls[0] == 4


def test_api_privacy_roles_and_selector_rejection():
    snapshot = authenticated_snapshot()

    class StaticService:
        def get_calendar(self, current_user=None):
            result = json.loads(json.dumps(snapshot))
            if not isinstance(current_user, dict) or current_user.get("role") not in {"owner", "adult", "child", "wall_display"}:
                result["events"] = []
                result["calendars"] = []
            return result

    with api_environment() as client:
        calendar_module.calendar_service = StaticService()
        anonymous = client.get("/api/family/calendar?role=owner&entity_id=calendar.other&start=2000-01-01&end=2100-01-01")
        assert anonymous.status_code == 200
        assert anonymous.json()["today_count"] == 1
        assert anonymous.json()["events"] == []
        assert anonymous.json()["calendars"] == []
        assert "Tandlæge" not in anonymous.text
        assert "Green calendar" not in anonymous.text

        for role in ["owner", "adult", "child", "wall_display"]:
            client.cookies.clear()
            login(client, role)
            response = client.get("/api/family/calendar?role=anonymous")
            assert response.status_code == 200
            assert {item["label"] for item in response.json()["calendars"]} == {
                "Green calendar",
                "Blue calendar",
                "Violet calendar",
                "Shared calendar",
            }
            assert "Tandlæge" in response.text
            assert "private description" not in response.text
            assert "private location" not in response.text
            assert "calendar.example" not in response.text

        route = next(item for item in app.routes if getattr(item, "path", "") == "/api/family/calendar")
        assert route.methods == {"GET"}
        assert client.get("/api/family/weather").status_code == 200


def test_frontend_calendar_is_safe_and_role_aware():
    javascript = (ROOT / "app/static/js/family.js").read_text()
    stylesheet = (ROOT / "app/static/css/calendar.css").read_text()
    template = (ROOT / "app/static/index.html").read_text()

    assert 'data-family-card="calendar"' in template
    assert 'refreshSource("/api/family/calendar", renderCalendar' in javascript
    assert 'fetch(url, { credentials: "same-origin" })' in javascript
    assert "method:" not in javascript
    assert "textContent" in javascript
    assert "innerHTML" not in javascript
    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert "Authorization" not in javascript
    assert "HOME_ASSISTANT" not in javascript
    assert not re.search(r"\b(POST|PUT|PATCH|DELETE)\b", javascript, re.IGNORECASE)
    assert "renderAnonymousCalendar" in javascript
    assert "calendar.events || []" in javascript
    for color in ["green", "blue", "violet", "yellow"]:
        assert f"calendar-color-{color}" in stylesheet
    assert 'body[data-family-role="child"] .calendar-event' in stylesheet
    assert 'body[data-family-role="wall_display"] .calendar-card' in stylesheet
    for wording in ["I dag", "I morgen", "Hele dagen", "I gang nu"]:
        assert wording in javascript


if __name__ == "__main__":
    for test in [
        test_configuration_parsing_and_rejection,
        test_client_uses_configured_get_endpoints_and_server_range,
        test_client_handles_failures_and_partial_results_safely,
        test_normalization_is_safe_and_deterministic,
        test_sorting_limit_cache_stale_and_concurrency,
        test_api_privacy_roles_and_selector_rejection,
        test_frontend_calendar_is_safe_and_role_aware,
    ]:
        test()
    print("Calendar integration tests OK")
