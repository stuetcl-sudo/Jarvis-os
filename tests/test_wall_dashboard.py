import math
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.main_auth import app
from app.wall_view import WALL_ASSET_VERSION_PLACEHOLDER, render_wall_page, wall_asset_version
from app.weather import PUBLIC_FIELDS, _safe_uv_index, normalize_weather

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def wall_environment():
    previous = config.DB_PATH
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "wall.db")
        init_db()
        initialize_auth_tables()
        client = TestClient(app, follow_redirects=False)
        try:
            yield client
        finally:
            client.close()
            config.DB_PATH = previous


def credential():
    return "".join(["Wall", "Display", "Pass", "-42!"])


def login(client, role):
    username = f"wall-{role}"
    auth_service.create_user(username, f"Wall {role}", role, credential())
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": credential()},
    )
    assert response.status_code == 200, response.text


def weather_payload():
    return {
        "state": "sunny",
        "attributes": {"temperature": 20, "temperature_unit": "°C"},
    }


def forecast_payload():
    return {"weather.example": {"forecast": []}}


def parse_event_bounds(event):
    if event.get("all_day"):
        start = datetime.fromisoformat(event["start"])
        end = datetime.fromisoformat(event["end"])
    else:
        start = datetime.fromisoformat(event["start"])
        end = datetime.fromisoformat(event["end"])
    if end <= start:
        return None
    return start, end


def intersects_day(event, day_start):
    bounds = parse_event_bounds(event)
    if not bounds:
        return False
    start, end = bounds
    day_end = day_start + timedelta(days=1)
    return start < day_end and end > day_start


def select_reference(events, now):
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)

    def ordered(candidates):
        return sorted(
            candidates,
            key=lambda event: (
                parse_event_bounds(event)[0],
                parse_event_bounds(event)[1],
                event.get("title", ""),
            ),
        )

    remaining_today = ordered(
        event
        for event in events
        if parse_event_bounds(event)
        and intersects_day(event, today)
        and parse_event_bounds(event)[1] > now
    )
    if remaining_today:
        return remaining_today[0], "today"

    tomorrow_events = ordered(
        event
        for event in events
        if parse_event_bounds(event) and intersects_day(event, tomorrow)
    )
    return (tomorrow_events[0], "tomorrow") if tomorrow_events else None


def test_wall_route_roles_and_admin_policy():
    with wall_environment() as client:
        anonymous = client.get("/wall?role=owner")
        assert anonymous.status_code == 303
        assert anonymous.headers["location"] == "/login?next=/wall"

    for role in ["owner", "adult", "child", "wall_display"]:
        with wall_environment() as client:
            login(client, role)
            wall = client.get("/wall?role=owner")
            assert wall.status_code == 200
            assert 'data-wall-dashboard="true"' in wall.text
            admin = client.get("/admin")
            assert admin.status_code == (200 if role == "owner" else 403)


def test_wall_html_assets_roles_and_cache_busting():
    expected_version = wall_asset_version()
    assert re.fullmatch(r"[0-9a-f]{12}", expected_version)

    for role in ["owner", "adult", "child", "wall_display"]:
        with wall_environment() as client:
            login(client, role)
            page = client.get("/wall").text
            assert 'id="wallClock"' in page
            assert 'id="wallUvIndex"' in page
            assert 'id="wallTodayEvents"' in page
            assert 'id="wallNextEvent"' in page
            assert 'id="wallRoutinePictogram"' in page
            assert 'class="wall-right-column"' in page
            assert 'id="routineEditButton"' not in page
            assert WALL_ASSET_VERSION_PLACEHOLDER not in page
            assert f'/static/css/wall.css?v={expected_version}' in page
            assert f'/static/css/wall-details.css?v={expected_version}' in page
            assert f'/static/js/wall.js?v={expected_version}' in page
            assert page.index('class="wall-card wall-next-card"') < page.index(
                'class="wall-card wall-routine-card"'
            )
            assert ('href="/admin"' in page) is (role == "owner")

    rendered = render_wall_page({"role": "wall_display"})
    assert WALL_ASSET_VERSION_PLACEHOLDER not in rendered

    with wall_environment() as client:
        for asset in [
            "/static/css/wall.css",
            "/static/css/wall-details.css",
            "/static/js/wall.js",
            "/static/pictograms/routines.svg",
        ]:
            response = client.get(asset)
            assert response.status_code == 200, asset
            assert response.text.strip()


def test_wall_frontend_security_and_fixed_endpoints():
    javascript = (ROOT / "app/static/js/wall.js").read_text()
    template = (ROOT / "app/static/wall.html").read_text()
    styles = (ROOT / "app/static/css/wall.css").read_text()
    details = (ROOT / "app/static/css/wall-details.css").read_text()
    combined = javascript + template + styles + details

    for forbidden in [
        "localStorage",
        "sessionStorage",
        "Authorization",
        "HOME_ASSISTANT",
        "Home Assistant",
        "eval(",
    ]:
        assert forbidden not in combined
    assert "innerHTML" not in javascript
    assert "textContent" in javascript
    assert "createElement" in javascript
    assert "wallRoutineIds" in javascript
    assert "wallRoutineEndpoints" in javascript
    assert "requestFullscreen" in javascript
    assert "visibilitychange" in javascript

    literal_fetches = set(re.findall(r'fetch\("([^"?]+)"', javascript))
    assert literal_fetches == {
        "/api/family/weather",
        "/api/family/calendar",
        "/api/family/routines",
        "/api/auth/me",
        "/api/auth/logout",
    }
    for endpoint in [
        "/api/family/routines/morning/complete",
        "/api/family/routines/morning/back",
        "/api/family/routines/evening/complete",
        "/api/family/routines/evening/back",
    ]:
        assert endpoint in javascript

    without_namespace = combined.replace("http://www.w3.org/2000/svg", "")
    assert "http://" not in without_namespace
    assert "https://" not in without_namespace


def test_uv_backend_validation_and_wall_categories():
    valid_values = [(0, 0), ("0", 0), (2, 2), ("5.5", 5.5), (11, 11)]
    for supplied, expected in valid_values:
        assert _safe_uv_index(supplied) == expected
        normalized = normalize_weather(
            weather_payload(),
            forecast_payload(),
            "weather.example",
            {"entity_id": "sensor.openuv_current_uv_index", "state": supplied},
        )
        assert normalized["uv_index"] == expected
        assert set(normalized) == PUBLIC_FIELDS

    for invalid in [None, "", True, False, "invalid", -1, float("nan"), float("inf")]:
        assert _safe_uv_index(invalid) is None

    javascript = (ROOT / "app/static/js/wall.js").read_text()
    assert "function validUvIndex(value)" in javascript
    assert "number !== null && number >= 0" in javascript
    assert "renderUvIndex(data.uv_index)" in javascript
    for label in ["Lav", "Moderat", "Høj", "Meget høj", "Ekstrem"]:
        assert f'"{label}"' in javascript
    assert math.isfinite(float(_safe_uv_index("7")))


def test_next_appointment_sorts_unsorted_candidates_and_stops_after_tomorrow():
    now = datetime.fromisoformat("2026-07-01T15:00:00+02:00")
    unsorted = [
        {
            "title": "Sen i morgen",
            "start": "2026-07-02T18:00:00+02:00",
            "end": "2026-07-02T19:00:00+02:00",
            "all_day": False,
        },
        {
            "title": "Senere i dag",
            "start": "2026-07-01T17:00:00+02:00",
            "end": "2026-07-01T18:00:00+02:00",
            "all_day": False,
        },
        {
            "title": "Tidlig i morgen",
            "start": "2026-07-02T08:00:00+02:00",
            "end": "2026-07-02T09:00:00+02:00",
            "all_day": False,
        },
        {
            "title": "Tidligst i dag",
            "start": "2026-07-01T16:00:00+02:00",
            "end": "2026-07-01T16:30:00+02:00",
            "all_day": False,
        },
        {
            "title": "Afsluttet",
            "start": "2026-07-01T09:00:00+02:00",
            "end": "2026-07-01T10:00:00+02:00",
            "all_day": False,
        },
        {
            "title": "For langt fremme",
            "start": "2026-07-03T08:00:00+02:00",
            "end": "2026-07-03T09:00:00+02:00",
            "all_day": False,
        },
    ]
    selected, day = select_reference(unsorted, now)
    assert selected["title"] == "Tidligst i dag"
    assert day == "today"

    without_today = [event for event in unsorted if "i dag" not in event["title"] and event["title"] != "Afsluttet"]
    selected, day = select_reference(without_today, now)
    assert selected["title"] == "Tidlig i morgen"
    assert day == "tomorrow"

    all_day_tomorrow = {
        "title": "Heldagsaftale",
        "start": "2026-07-02T00:00:00+02:00",
        "end": "2026-07-03T00:00:00+02:00",
        "all_day": True,
    }
    crossing_midnight = {
        "title": "Krydser midnat",
        "start": "2026-07-01T23:30:00+02:00",
        "end": "2026-07-02T00:30:00+02:00",
        "all_day": False,
    }
    selected, day = select_reference([all_day_tomorrow, crossing_midnight], now)
    assert selected["title"] == "Krydser midnat"
    assert day == "today"
    assert select_reference([unsorted[-1]], now) is None

    javascript = (ROOT / "app/static/js/wall.js").read_text()
    assert "function compareAppointmentCandidates" in javascript
    assert ".sort(compareAppointmentCandidates)" in javascript
    assert "end <= start" in javascript
    assert "tomorrowEvents[0]" in javascript
    assert "Ingen aftaler i dag eller i morgen" in javascript
    assert "Ingen flere aftaler i dag" not in javascript


def test_apparent_temperature_validation_remains_strict():
    javascript = (ROOT / "app/static/js/wall.js").read_text()
    assert "function finiteNumber(value)" in javascript
    assert 'value === null || value === undefined || value === ""' in javascript
    assert 'typeof value === "boolean"' in javascript
    assert "Number.isFinite(number)" in javascript
    assert "apparentTemperatureText(data.apparent_temperature" in javascript


def test_right_column_natural_flow_and_responsive_layout():
    template = (ROOT / "app/static/wall.html").read_text()
    stylesheet = (ROOT / "app/static/css/wall.css").read_text()
    right_column_start = template.index('class="wall-right-column"')
    next_card = template.index('class="wall-card wall-next-card"', right_column_start)
    tomorrow_label = template.index('id="wallNextDay"', next_card)
    routine_card = template.index('class="wall-card wall-routine-card"', next_card)
    assert right_column_start < next_card < tomorrow_label < routine_card

    assert ".wall-right-column" in stylesheet
    assert "flex-direction: column" in stylesheet
    assert "height: auto" in stylesheet
    assert "position: static" in stylesheet
    assert "overflow-wrap: anywhere" in stylesheet
    assert "word-break: break-word" in stylesheet
    assert "position: absolute" not in stylesheet
    assert "@media (orientation: landscape) and (max-height: 600px)" in stylesheet
    assert "height: 100dvh" in stylesheet
    assert "@media (max-width: 760px), (orientation: portrait)" in stylesheet
    assert "overflow-x: hidden" in stylesheet
    assert "min-height: 44px" in stylesheet
    assert "min-height: 48px" in stylesheet


def test_wall_sources_are_readable_and_validation_covers_assets():
    javascript = (ROOT / "app/static/js/wall.js").read_text()
    stylesheet = (ROOT / "app/static/css/wall.css").read_text()
    details = (ROOT / "app/static/css/wall-details.css").read_text()
    validation = (ROOT / "scripts/validate.sh").read_text()

    assert len(javascript.splitlines()) > 300
    assert len(stylesheet.splitlines()) > 300
    assert len(details.splitlines()) > 30
    assert max(map(len, javascript.splitlines())) < 180
    assert max(map(len, stylesheet.splitlines())) < 180
    assert 'tests/test_wall_dashboard.py' in validation
    assert 'check_live_route "/static/js/wall.js"' in validation
    assert 'check_live_route "/static/css/wall.css"' in validation
    assert 'check_live_route "/static/css/wall-details.css"' in validation


if __name__ == "__main__":
    for test in [
        test_wall_route_roles_and_admin_policy,
        test_wall_html_assets_roles_and_cache_busting,
        test_wall_frontend_security_and_fixed_endpoints,
        test_uv_backend_validation_and_wall_categories,
        test_next_appointment_sorts_unsorted_candidates_and_stops_after_tomorrow,
        test_apparent_temperature_validation_remains_strict,
        test_right_column_natural_flow_and_responsive_layout,
        test_wall_sources_are_readable_and_validation_covers_assets,
    ]:
        test()
    print("Wall dashboard tests OK")
