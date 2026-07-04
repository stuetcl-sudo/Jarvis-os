import tempfile
from contextlib import contextmanager
from pathlib import Path

from app import config
from app.screen_registry import get_screen, upsert_screen
from app.wall_view import render_wall_page


@contextmanager
def screen_environment():
    previous = config.DB_PATH
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "screens.db")
        try:
            yield
        finally:
            config.DB_PATH = previous


def test_default_wall_layout_uses_equal_module_sizes():
    with screen_environment():
        wall = get_screen("wall")
        assert wall["module_layout"] == {
            "routine": "large",
            "calendar": "large",
            "weather": "large",
            "meal": "large",
            "tasks": "large",
            "home": "small",
        }
        assert wall["display_options"] == {"show_admin_link": False, "show_safety_status": True}


def test_screen_registry_persists_module_size_layout_and_display_options():
    with screen_environment():
        created = upsert_screen(
            "Stuen",
            "stuen",
            "wall-tablet",
            ["calendar", "weather", "meal"],
            module_layout={"calendar": "full", "weather": "small", "meal": "medium"},
            display_options={"show_admin_link": True, "show_safety_status": False},
        )
        assert created["module_layout"] == {"calendar": "full", "weather": "small", "meal": "medium"}
        assert created["display_options"] == {"show_admin_link": True, "show_safety_status": False}

        reloaded = get_screen("stuen")
        assert reloaded["module_layout"] == created["module_layout"]
        assert reloaded["display_options"] == created["display_options"]
        assert reloaded["modules"] == ["calendar", "weather", "meal"]


def test_screen_registry_rejects_invalid_module_size():
    with screen_environment():
        try:
            upsert_screen("Broken", "broken", "wall-tablet", ["weather"], module_layout={"weather": "giant"})
        except ValueError as exc:
            assert "module size" in str(exc)
        else:
            raise AssertionError("invalid module size accepted")


def test_wall_page_applies_configured_module_size_css_and_status_badge():
    with screen_environment():
        upsert_screen(
            "Stuen",
            "stuen",
            "wall-tablet",
            ["calendar", "weather"],
            module_layout={"calendar": "full", "weather": "small"},
            display_options={"show_admin_link": True, "show_safety_status": False},
        )
        page = render_wall_page({"role": "owner"}, "stuen")
        assert 'data-wall-screen-slug="stuen"' in page
        assert 'id="wallHomeStatusBadge"' in page
        assert 'id="wallHomeStatusText"' in page
        assert 'href="/admin">Administration</a>' in page
        assert '#wallSafetyStrip{display:none!important}' in page
        assert 'body[data-wall-dashboard="true"] .family-grid{align-items:stretch}' in page
        assert 'body[data-wall-dashboard="true"] [data-family-card="home"]{display:none!important}' in page
        assert '[data-family-card="meal"]{display:none!important}' in page
        assert 'body[data-wall-dashboard="true"] .calendar-card{grid-column:1 / -1;min-height:340px}' in page
        assert 'body[data-wall-dashboard="true"] .weather-card{grid-column:span 3;min-height:190px}' in page
        assert '@media(min-width:1280px)' in page
        assert '@media(min-width:1181px) and (max-width:1279px)' in page
        assert '@media(min-width:921px) and (max-width:1180px)' in page
        assert '@media(max-width:920px)' not in page


if __name__ == "__main__":
    for test in [
        test_default_wall_layout_uses_equal_module_sizes,
        test_screen_registry_persists_module_size_layout_and_display_options,
        test_screen_registry_rejects_invalid_module_size,
        test_wall_page_applies_configured_module_size_css_and_status_badge,
    ]:
        test()
    print("Screen module layout tests OK")
