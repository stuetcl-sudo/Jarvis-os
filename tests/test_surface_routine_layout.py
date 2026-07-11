from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_surface_routine_layout_is_fixed_and_text_safe():
    polish = (ROOT / "app/static/css/wall-final-polish.css").read_text(encoding="utf-8")
    routine = (ROOT / "app/static/css/wall-surface-routine.css").read_text(encoding="utf-8")
    compact = routine.replace(" ", "").replace("\n", "")

    assert '@importurl("/static/css/wall-surface-routine.css")' in polish.replace(" ", "").replace("\n", "")
    assert 'data-wall-screen-profile="surface"].family-grid.routine-card{' in compact
    assert "height:clamp(310px,38vh,340px)!important" in compact
    assert "grid-template-columns:148pxminmax(0,1fr)!important" in compact
    assert ".routine-panel{display:contents!important" in compact
    assert ".routine-copy{" in compact
    assert "grid-template-rows:autoautominmax(0,1fr)autoautoauto!important" in compact
    assert "-webkit-line-clamp:2!important" in compact
    assert "font-size:clamp(25px,2.45vw,34px)!important" in compact
    assert "grid-template-columns:minmax(92px,0.8fr)minmax(132px,1.2fr)!important" in compact
    assert "grid-template-columns:repeat(7,minmax(0,auto))!important" in compact


if __name__ == "__main__":
    test_surface_routine_layout_is_fixed_and_text_safe()
    print("Surface routine layout tests OK")
