from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
FAMILY_CALENDAR = (ROOT / "app/static/js/family-calendar.js").read_text(encoding="utf-8")
CALENDAR_RANGE_CSS = (ROOT / "app/static/css/calendar-range.css").read_text(encoding="utf-8")
WALL_HTML = (ROOT / "app/static/wall.html").read_text(encoding="utf-8")
WALL_CALENDAR = (ROOT / "app/static/js/wall-calendar.js").read_text(encoding="utf-8")
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


def test_all_day_end_date_remains_exclusive_reference():
    start = datetime(2026, 7, 2)
    end = datetime(2026, 7, 3)

    def intersects(day):
        day_end = day + timedelta(days=1)
        return start < day_end and end > day

    assert intersects(datetime(2026, 7, 2)) is True
    assert intersects(datetime(2026, 7, 3)) is False


def test_wall_dashboard_separates_today_from_tomorrow():
    assert "<h2>I morgen</h2>" in WALL_HTML
    assert "Næste aftale" not in WALL_HTML
    assert "Ingen aftaler i morgen" in WALL_HTML
    assert '/static/js/wall-calendar.js?v=__WALL_ASSET_VERSION__' in WALL_HTML
    assert 'const tomorrow = tomorrowKey(now);' in WALL_CALENDAR
    assert 'eventIntersectsDate(event, tomorrow)' in WALL_CALENDAR
    assert 'day: "tomorrow"' in WALL_CALENDAR
    assert "remainingToday" not in WALL_CALENDAR
    assert 'event?.title || "Ingen aftaler i morgen"' in WALL_CALENDAR
    assert 'STATIC_ROOT / "js" / "wall-calendar.js"' in WALL_VIEW


def test_v011_calendar_enhancements_do_not_change_api_or_security():
    combined = FAMILY_CALENDAR + "\n" + WALL_CALENDAR
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
        test_all_day_end_date_remains_exclusive_reference,
        test_wall_dashboard_separates_today_from_tomorrow,
        test_v011_calendar_enhancements_do_not_change_api_or_security,
    ]:
        test()
    print("Family dashboard v0.11 tests OK")
