from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
UV_JS = (ROOT / "app/static/js/family-uv.js").read_text(encoding="utf-8")
WEATHER_CSS = (ROOT / "app/static/css/weather.css").read_text(encoding="utf-8")
WEATHER_BACKEND = (ROOT / "app/weather.py").read_text(encoding="utf-8")


def test_uv_indicator_is_present_on_family_and_wall_dashboard():
    assert 'id="weatherUv"' in INDEX
    assert 'id="weatherUvValue"' in INDEX
    assert 'id="weatherUvLabel"' in INDEX
    assert '/static/js/family-uv.js' in INDEX
    assert 'data-family-card="weather"' in INDEX


def test_uv_uses_simple_green_yellow_red_categories():
    assert 'value <= 2' in UV_JS
    assert '{ key: "green", label: "Lav UV" }' in UV_JS
    assert 'value <= 5' in UV_JS
    assert '{ key: "yellow", label: "Solcreme hvis du er længe ude" }' in UV_JS
    assert 'value <= 7' in UV_JS
    assert '{ key: "red", label: "Tag solcreme på" }' in UV_JS
    assert '{ key: "red", label: "Solcreme, skygge og pause" }' in UV_JS
    assert 'weather-uv-${category.key}' in UV_JS
    assert 'badge.setAttribute("aria-label", `${uv.label} ${formatted}. ${category.label}`)' in UV_JS
    assert 'valueElement.textContent = `${uv.label} ${formatted}`' in UV_JS


def test_uv_frontend_is_read_only_and_safe():
    assert 'fetch("/api/family/weather", { credentials: "same-origin" })' in UV_JS
    for forbidden in [
        'method: "POST"',
        'method: "PUT"',
        'method: "PATCH"',
        'method: "DELETE"',
        "innerHTML",
        "insertAdjacentHTML",
        "localStorage",
        "sessionStorage",
        "eval(",
        "Authorization",
    ]:
        assert forbidden not in UV_JS


def test_uv_colors_are_accessible_on_child_and_wall_views():
    for selector in [
        ".weather-uv-green",
        ".weather-uv-yellow",
        ".weather-uv-red",
        'body[data-family-role="child"] .weather-uv',
        'body[data-family-role="wall_display"] .weather-uv',
    ]:
        assert selector in WEATHER_CSS
    assert "#18794e" in WEATHER_CSS
    assert "#f4c542" in WEATHER_CSS
    assert "#c93434" in WEATHER_CSS
    assert 'id="weatherUvLabel">Ukendt</span>' in INDEX


def test_uv_value_remains_a_safe_public_weather_field():
    assert '"uv_index"' in WEATHER_BACKEND
    assert "_safe_uv_index" in WEATHER_BACKEND


if __name__ == "__main__":
    for test in [
        test_uv_indicator_is_present_on_family_and_wall_dashboard,
        test_uv_uses_simple_green_yellow_red_categories,
        test_uv_frontend_is_read_only_and_safe,
        test_uv_colors_are_accessible_on_child_and_wall_views,
        test_uv_value_remains_a_safe_public_weather_field,
    ]:
        test()
    print("UV color v0.13 tests OK")
