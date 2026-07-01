import math
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.main_auth import app
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
    response = client.post("/api/auth/login", json={"username": username, "password": credential()})
    assert response.status_code == 200, response.text


def weather_payload():
    return {
        "state": "sunny",
        "attributes": {"temperature": 20, "temperature_unit": "°C"},
    }


def forecast_payload():
    return {"weather.example": {"forecast": []}}


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


def test_wall_html_assets_and_role_navigation():
    for role in ["owner", "adult", "child", "wall_display"]:
        with wall_environment() as client:
            login(client, role)
            page = client.get("/wall").text
            assert 'id="wallClock"' in page
            assert 'id="wallDate"' in page
            assert 'id="wallUvIndex"' in page
            assert 'id="wallTodayEvents"' in page
            assert 'id="wallNextEvent"' in page
            assert 'id="wallNextDay"' in page
            assert 'id="wallForecast"' in page
            assert 'id="wallRoutinePictogram"' in page
            assert 'id="wallFullscreen"' in page
            assert 'id="routineEditButton"' not in page
            assert "Action Queue" not in page and "Docker status" not in page
            assert ('href="/admin"' in page) is (role == "owner")
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
    details = (ROOT / "app/static/css/wall-details.css").read_text()
    combined = javascript + template + details
    assert "localStorage" not in combined
    assert "sessionStorage" not in combined
    assert "Authorization" not in combined
    assert "HOME_ASSISTANT" not in combined and "Home Assistant" not in combined
    assert "eval(" not in combined
    assert "innerHTML" not in javascript
    assert "textContent" in javascript and "createElement" in javascript
    assert "wallRoutineIds" in javascript
    assert "wallRoutineEndpoints" in javascript
    assert "button.disabled=value" in javascript
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
    assert "http://" not in without_namespace and "https://" not in without_namespace
    assert "<script src=\"http" not in template and "<link href=\"http" not in template


def test_uv_backend_validation_and_public_field():
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

    for invalid in [None, "", True, False, "invalid", -1, float("nan"), float("inf"), float("-inf")]:
        assert _safe_uv_index(invalid) is None
    missing = normalize_weather(weather_payload(), forecast_payload(), "weather.example")
    assert missing["uv_index"] is None
    assert math.isfinite(float(_safe_uv_index("7")))


def test_uv_wall_rendering_categories_and_compact_style():
    javascript = (ROOT / "app/static/js/wall.js").read_text()
    details = (ROOT / "app/static/css/wall-details.css").read_text()
    assert "function validUvIndex(value)" in javascript
    assert "number!==null&&number>=0?number:null" in javascript
    assert "renderUvIndex(data.uv_index)" in javascript
    assert "node.hidden=number===null" in javascript
    assert 'node.textContent=`UV ${numberText(number)} · ${uvCategory(number)}`' in javascript
    for boundary, label in [(3, "Lav"), (6, "Moderat"), (8, "Høj"), (11, "Meget høj")]:
        assert f"if(value<{boundary})return\"{label}\"" in javascript
    assert 'return"Ekstrem"' in javascript
    assert ".wall-uv[hidden]{display:none}" in details
    assert "white-space:nowrap" in details
    assert "font-size:13px" in details


def test_next_appointment_today_then_tomorrow_only():
    javascript = (ROOT / "app/static/js/wall.js").read_text()
    assert "function selectNextAppointment(events,now=new Date())" in javascript
    assert "eventIntersectsDate(event,today)&&eventIsCurrentOrFuture(event,now)" in javascript
    assert 'if(remainingToday)return{event:remainingToday,day:"today"}' in javascript
    assert "const firstTomorrow=list.find(event=>eventIntersectsDate(event,tomorrow))" in javascript
    assert 'return firstTomorrow?{event:firstTomorrow,day:"tomorrow"}:null' in javascript
    assert 'selection?.day==="tomorrow"?"I morgen":""' in javascript
    assert "eventIntersectsDate(event,todayKey(now))" in javascript
    assert "bounds.end>now" in javascript
    assert "bounds.start<end&&bounds.end>start" in javascript
    assert 'if(event.all_day)return"Hele dagen"' in javascript
    assert 'return"I gang nu"' in javascript
    assert "tomorrow.setDate(tomorrow.getDate()+1)" in javascript
    assert "Ingen flere aftaler i dag" in javascript
    assert "dayAfterTomorrow" not in javascript


def test_apparent_temperature_requires_a_real_finite_value():
    javascript = (ROOT / "app/static/js/wall.js").read_text()
    assert "function finiteNumber(value)" in javascript
    assert 'value===null||value===undefined||value===""||typeof value==="boolean"' in javascript
    assert "Number.isFinite(number)?number:null" in javascript
    assert 'function apparentTemperatureText(value,unit="")' in javascript
    assert 'return number===null?"":`Føles som ${numberText(number,unit)}`' in javascript
    assert "apparentTemperatureText(data.apparent_temperature" in javascript
    assert "Number.isFinite(Number(data.apparent_temperature))" not in javascript
    assert "if(number)" not in javascript


def test_compact_tablet_landscape_and_portrait_layout():
    stylesheet = (ROOT / "app/static/css/wall.css").read_text()
    assert 'grid-template-areas:"header header" "notice notice" "calendar next" "calendar routine" "forecast forecast"' in stylesheet
    assert ".wall-calendar-card{grid-area:calendar" in stylesheet
    assert ".wall-next-card{grid-area:next" in stylesheet
    assert ".wall-routine-card{grid-area:routine" in stylesheet
    assert "@media(orientation:landscape) and (max-height:600px)" in stylesheet
    assert ".wall-forecast-section{display:none}" in stylesheet
    assert "height:100dvh" in stylesheet
    assert ".wall-menu a,.wall-menu button{min-height:44px" in stylesheet
    assert ".wall-routine-actions .wall-primary-action{min-width:150px;min-height:48px" in stylesheet
    assert "@media(max-width:760px),(orientation:portrait)" in stylesheet
    assert 'grid-template-areas:"header" "notice" "calendar" "next" "routine" "forecast"' in stylesheet
    assert "overflow-x:hidden" in stylesheet


def test_wall_states_labels_and_responsive_presentation():
    javascript = (ROOT / "app/static/js/wall.js").read_text()
    stylesheet = (ROOT / "app/static/css/wall.css").read_text()
    details = (ROOT / "app/static/css/wall-details.css").read_text()
    for status in ["ok", "stale", "not_configured", "unavailable"]:
        assert status in javascript
    assert "partial" in javascript
    assert "Ingen aftaler i dag" in (ROOT / "app/static/wall.html").read_text()
    for color in ["green", "blue", "violet", "yellow"]:
        assert f"calendar-color-{color}" in stylesheet
        assert f"calendar-color-{color}" in details
    assert 'new Intl.DateTimeFormat("da-DK"' in javascript
    assert "min-height:44px" in stylesheet
    assert "min-height:48px" in stylesheet
    assert "overflow-x:hidden" in stylesheet


if __name__ == "__main__":
    for test in [
        test_wall_route_roles_and_admin_policy,
        test_wall_html_assets_and_role_navigation,
        test_wall_frontend_security_and_fixed_endpoints,
        test_uv_backend_validation_and_public_field,
        test_uv_wall_rendering_categories_and_compact_style,
        test_next_appointment_today_then_tomorrow_only,
        test_apparent_temperature_requires_a_real_finite_value,
        test_compact_tablet_landscape_and_portrait_layout,
        test_wall_states_labels_and_responsive_presentation,
    ]:
        test()
    print("Wall dashboard tests OK")
