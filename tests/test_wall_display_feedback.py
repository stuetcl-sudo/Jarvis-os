from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_wall_display_uses_more_compact_type_and_cards():
    stylesheet = (ROOT / "app/static/css/wall-mode.css").read_text(encoding="utf-8")

    assert 'body[data-wall-dashboard="true"] .family-header' in stylesheet
    assert 'min-height: clamp(120px, 15vw, 170px)' in stylesheet
    assert 'body[data-wall-dashboard="true"] .family-header h1' in stylesheet
    assert 'font-size: clamp(42px, 5.4vw, 74px)' in stylesheet
    assert 'body[data-wall-dashboard="true"] .family-card' in stylesheet
    assert 'min-height: 320px' in stylesheet


def test_wall_display_task_lists_are_limited_and_surface_balanced():
    source = (ROOT / "app/static/js/family-tasks.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "app/static/css/wall-surface.css").read_text(encoding="utf-8")

    assert "WALL_SHOPPING_PREVIEW_LIMIT = 5" in source
    assert "items.slice(0, WALL_SHOPPING_PREVIEW_LIMIT)" in source
    assert "family-task-list-shopping-list" in source
    assert "family-task-more" in source
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in stylesheet


def test_wall_display_uv_is_guidance_and_weather_refreshes_faster():
    source = (ROOT / "app/static/js/family-uv.js").read_text(encoding="utf-8")
    weather = (ROOT / "app/weather.py").read_text(encoding="utf-8")
    config = (ROOT / "app/config.py").read_text(encoding="utf-8")

    assert "UV_REFRESH_INTERVAL_MS = 120000" in source
    assert "uv_max_index" in source
    assert 'label: "UV nu"' in source
    assert 'label: "UV max"' in source
    assert 'label: "Lav UV"' in source
    assert "Tag solcreme på" in source
    assert "isWallDisplay() && value < 0.5" not in source
    assert "DEFAULT_UV_MAX_ENTITY" in weather
    assert 'env_positive_int("WEATHER_CACHE_SECONDS", 120)' in config


def test_wall_screen_profiles_are_loaded_and_adaptive():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    source = (ROOT / "app/static/js/wall-mode.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "app/static/css/wall-profiles.css").read_text(encoding="utf-8")

    assert "/static/css/wall-profiles.css" in html
    assert "dataset.wallScreenProfile" in source
    assert 'return "mobile"' in source
    assert 'return "square"' in source
    assert 'return "tablet"' in source
    assert 'return "wide"' in source
    assert 'data-wall-screen-profile="square"' in stylesheet
    assert 'data-wall-screen-profile="tablet"' in stylesheet
    assert 'data-wall-screen-profile="mobile"' in stylesheet
    assert ".routine-card" in stylesheet
    assert "grid-column: 1 / -1" in stylesheet
    assert "word-break: normal" in stylesheet


def test_family_sources_fail_independently():
    source = (ROOT / "app/static/js/family.js").read_text(encoding="utf-8")

    assert "async function refreshSource(url, onSuccess, onFailure)" in source
    assert "Promise.allSettled([" in source
    assert "Promise.all([" not in source
    assert 'refreshSource("/api/mission", renderMission, renderUnavailable)' in source
    assert 'refreshSource("/api/family/weather", renderWeather, renderWeatherFailure)' in source
    assert 'refreshSource("/api/family/calendar", renderCalendar, renderCalendarFailure)' in source
    assert 'refreshSource("/api/health", renderHealth' in source

    assert "function renderWeatherFailure()" in source
    assert 'stale.textContent = "Viser senest hentede vejrdata"' in source
    assert "function renderCalendarFailure()" in source
    assert 'notice.textContent = "Viser senest hentede kalenderdata"' in source


def test():
    test_wall_display_uses_more_compact_type_and_cards()
    test_wall_display_task_lists_are_limited_and_surface_balanced()
    test_wall_display_uv_is_guidance_and_weather_refreshes_faster()
    test_wall_screen_profiles_are_loaded_and_adaptive()
    test_family_sources_fail_independently()
    print("Wall display feedback tests OK")


if __name__ == "__main__":
    test()
