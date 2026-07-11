from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_surface_calendar_is_fixed_height_and_uses_two_columns():
    polish = (ROOT / "app/static/css/wall-final-polish.css").read_text(encoding="utf-8")
    calendar = (ROOT / "app/static/css/wall-surface-calendar.css").read_text(encoding="utf-8")
    compact = calendar.replace(" ", "").replace("\n", "")

    assert '@importurl("/static/css/wall-surface-calendar.css")' in polish.replace(" ", "").replace("\n", "")
    assert 'data-wall-screen-profile="surface"].family-grid.calendar-card{' in compact
    assert "height:clamp(350px,43vh,400px)!important" in compact
    assert "max-height:400px!important" in compact
    assert ".calendar-card-content{" in compact
    assert "overflow:hidden!important" in compact
    assert ".calendar-events:not([hidden]){" in compact
    assert "overflow-y:auto!important" in compact
    assert "overflow-x:hidden!important" in compact
    assert "scrollbar-gutter:stable!important" in compact
    assert 'data-calendar-days="1"].calendar-events{' in compact
    for days in (3, 5, 7):
        assert f'data-calendar-days="{days}"].calendar-events' in compact
    assert "grid-template-columns:repeat(2,minmax(0,1fr))!important" in compact


if __name__ == "__main__":
    test_surface_calendar_is_fixed_height_and_uses_two_columns()
    print("Surface calendar layout tests OK")
