from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_surface_calendar_matches_meal_row_and_uses_two_columns():
    polish = (ROOT / "app/static/css/wall-final-polish.css").read_text(encoding="utf-8")
    calendar = (ROOT / "app/static/css/wall-surface-calendar.css").read_text(encoding="utf-8")
    compact = calendar.replace(" ", "").replace("\n", "")

    assert '@importurl("/static/css/wall-surface-calendar.css")' in polish.replace(" ", "").replace("\n", "")
    assert 'data-wall-screen-profile="surface"].family-grid.calendar-card{' in compact
    assert "height:auto!important" in compact
    assert "min-height:0!important" in compact
    assert "max-height:none!important" in compact
    assert "align-self:stretch!important" in compact
    assert ".calendar-card-content{" in compact
    assert "height:100%!important" in compact
    assert "overflow:hidden!important" in compact
    assert ".calendar-events:not([hidden]){" in compact
    assert "align-content:stretch!important" in compact
    assert "grid-auto-rows:minmax(min-content,1fr)!important" in compact
    assert "overflow-y:auto!important" in compact
    assert "overflow-x:hidden!important" in compact
    assert "scrollbar-gutter:stable!important" in compact
    assert 'data-calendar-days="1"].calendar-events{' in compact
    for days in (3, 5, 7):
        assert f'data-calendar-days="{days}"].calendar-events' in compact
    assert "grid-template-columns:repeat(2,minmax(0,1fr))!important" in compact
    assert 'data-calendar-days="3"].calendar-day-group:nth-child(3){' in compact
    assert "grid-column:1/-1!important" in compact
    assert ".calendar-day-group{" in compact
    assert "flex-direction:column!important" in compact
    assert ".calendar-day-events{" in compact
    assert "overflow-y:auto!important" in compact


if __name__ == "__main__":
    test_surface_calendar_matches_meal_row_and_uses_two_columns()
    print("Surface calendar layout tests OK")
