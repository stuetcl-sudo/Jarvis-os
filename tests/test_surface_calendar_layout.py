from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_surface_calendar_prioritizes_today_and_keeps_internal_scroll():
    polish = (ROOT / "app/static/css/wall-final-polish.css").read_text(encoding="utf-8")
    calendar = (ROOT / "app/static/css/wall-surface-calendar.css").read_text(encoding="utf-8")
    compact = calendar.replace(" ", "").replace("\n", "")

    assert '@importurl("/static/css/wall-surface-calendar.css")' in polish.replace(" ", "").replace("\n", "")
    assert 'data-wall-screen-profile="surface"].family-grid{align-items:stretch!important' in compact
    assert 'data-wall-screen-profile="surface"].family-grid.calendar-card,' in compact
    assert 'data-wall-screen-profile="surface"].family-grid.meal-card{' in compact
    assert "height:100%!important" in compact
    assert "align-self:stretch!important" in compact
    assert ".calendar-events:not([hidden]){" in compact
    assert "overflow-y:auto!important" in compact
    assert "overflow-x:hidden!important" in compact
    assert "scrollbar-gutter:stable!important" in compact
    assert 'data-calendar-days="1"].calendar-events{' in compact
    for days in (3, 5, 7):
        assert f'data-calendar-days="{days}"].calendar-events' in compact
    assert "grid-template-columns:repeat(2,minmax(0,1fr))!important" in compact
    assert 'data-calendar-days="3"].calendar-day-group:first-child,' in compact
    assert 'data-calendar-days="5"].calendar-day-group:first-child,' in compact
    assert 'data-calendar-days="7"].calendar-day-group:first-child{' in compact
    assert "grid-column:1/-1!important" in compact
    assert "min-height:clamp(210px,26vh,270px)!important" in compact
    assert "box-shadow:inset0001pxrgba(125,211,252,0.24)!important" in compact
    assert 'data-calendar-days="5"].calendar-events,' in compact
    assert 'data-calendar-days="7"].calendar-events{' in compact
    assert "grid-auto-rows:minmax(150px,auto)!important" in compact
    assert "align-content:start!important" in compact
    assert 'data-calendar-days="5"].calendar-day-events,' in compact
    assert 'data-calendar-days="7"].calendar-day-events{' in compact
    assert "overflow-y:visible!important" in compact
    assert ".calendar-day-group:first-child.calendar-day-headingh3{" in compact
    assert "font-size:18px!important" in compact


if __name__ == "__main__":
    test_surface_calendar_prioritizes_today_and_keeps_internal_scroll()
    print("Surface calendar layout tests OK")
