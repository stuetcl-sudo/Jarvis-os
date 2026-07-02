from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
FAMILY_CALENDAR = (ROOT / "app/static/js/family-calendar.js").read_text(encoding="utf-8")
CALENDAR_RANGE_CSS = (ROOT / "app/static/css/calendar-range.css").read_text(encoding="utf-8")
WALL_MODE_JS = (ROOT / "app/static/js/wall-mode.js").read_text(encoding="utf-8")
WALL_MODE_CSS = (ROOT / "app/static/css/wall-mode.css").read_text(encoding="utf-8")
WALL_VIEW = (ROOT / "app/wall_view.py").read_text(encoding="utf-8")


def test_family_calendar_offers_supported_day_ranges():
    assert "Familiens kalender" in INDEX
    assert 'id="calendarRangeControls"' in INDEX
    assert '/static/css/calendar-range.css' in INDEX
    assert '/static/js/family-calendar.js' in INDEX
    for days in (1, 3, 5, 7):
        assert f'data-calendar-days="{days}"' in INDEX
        assert f"calendar-days-{days}" in CALENDAR_RANGE_CSS
    assert "calendarDayChoices = new Set([1, 3, 5, 7])" in FAMILY_CALENDAR
    assert 'pageRole === "wall_display"' in FAMILY_CALENDAR
    assert 'window.matchMedia("(max-width: 640px)")' in FAMILY_CALENDAR


def test_family_calendar_is_grouped_by_visible_day():
    for expected in [
        "function calendarRangeKeys",
        "function calendarEventBounds",
        "function calendarEventIntersectsDay",
        "function createCalendarDayGroup",
        'empty.textContent = index === 0 ? "Ingen aftaler i dag" : "Ingen aftaler"',
        "renderAuthenticatedCalendar = function renderAuthenticatedCalendarRange",
    ]:
        assert expected in FAMILY_CALENDAR
    assert "bounds.start < end && bounds.end > start" in FAMILY_CALENDAR
    assert "return new Date(parts[0], parts[1] - 1, parts[2]);" in FAMILY_CALENDAR
    assert "innerHTML" not in FAMILY_CALENDAR


def test_completed_events_disappear_but_ongoing_events_remain():
    now = datetime(2026, 7, 2, 20, 6)
    completed_end = datetime(2026, 7, 2, 12, 0)
    ongoing_end = datetime(2026, 7, 2, 21, 0)
    all_day_end = datetime(2026, 7, 3, 0, 0)

    assert completed_end > now is False
    assert ongoing_end > now is True
    assert all_day_end > now is True
    assert "function calendarEventIsCurrentOrUpcoming" in FAMILY_CALENDAR
    assert "return Boolean(bounds && bounds.end > now);" in FAMILY_CALENDAR
    assert "calendar.events.filter((event) => calendarEventIsCurrentOrUpcoming(event, now))" in FAMILY_CALENDAR
    assert "if (latestCalendarSnapshot) renderCalendarDays(latestCalendarSnapshot);" in FAMILY_CALENDAR
    assert "}, 30000);" in FAMILY_CALENDAR


def test_all_day_end_date_remains_exclusive_reference():
    start = datetime(2026, 7, 2)
    end = datetime(2026, 7, 3)

    def intersects(day):
        day_end = day + timedelta(days=1)
        return start < day_end and end > day

    assert intersects(datetime(2026, 7, 2)) is True
    assert intersects(datetime(2026, 7, 3)) is False


def test_wall_route_reuses_family_dashboard_in_shared_display_mode():
    assert "from app.family_view import render_family_page" in WALL_VIEW
    assert 'shared_display = {"role": "wall_display", "display_name": ""}' in WALL_VIEW
    assert "render_family_page(shared_display" in WALL_VIEW
    assert 'data-wall-dashboard="true"' in WALL_VIEW
    assert "WALL_TEMPLATE" not in WALL_VIEW
    assert "wall_asset_version" not in WALL_VIEW
    assert '<!-- WALL_DISPLAY_ACTIONS -->' in INDEX
    assert '/static/css/wall-mode.css' in INDEX
    assert '/static/js/wall-mode.js' in INDEX
    assert 'id="wallFullscreen"' in WALL_VIEW
    assert "requestFullscreen" in WALL_MODE_JS
    assert 'body[data-wall-dashboard="true"]' in WALL_MODE_CSS


def test_v011_calendar_and_wall_enhancements_do_not_change_api_or_storage():
    combined = FAMILY_CALENDAR + "\n" + WALL_MODE_JS
    for forbidden in [
        "fetch(",
        "localStorage",
        "sessionStorage",
        "URLSearchParams",
        "location.hash",
        "innerHTML",
        "insertAdjacentHTML",
        "eval(",
    ]:
        assert forbidden not in combined
    assert "/api/" not in combined


if __name__ == "__main__":
    for test in [
        test_family_calendar_offers_supported_day_ranges,
        test_family_calendar_is_grouped_by_visible_day,
        test_completed_events_disappear_but_ongoing_events_remain,
        test_all_day_end_date_remains_exclusive_reference,
        test_wall_route_reuses_family_dashboard_in_shared_display_mode,
        test_v011_calendar_and_wall_enhancements_do_not_change_api_or_storage,
    ]:
        test()
    print("Family dashboard v0.11 tests OK")
