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


def test_screen_registry_persists_module_size_layout():
    with screen_environment():
        created = upsert_screen(
            "Stuen",
            "stuen",
            "wall-tablet",
            ["calendar", "weather", "meal"],
            module_layout={"calendar": "full", "weather": "small", "meal": "medium"},
        )
        assert created["module_layout"] == {"calendar": "full", "weather": "small", "meal": "medium"}

        reloaded = get_screen("stuen")
        assert reloaded["module_layout"] == created["module_layout"]
        assert reloaded["modules"] == ["calendar", "weather", "meal"]


def test_screen_registry_rejects_invalid_module_size():
    with screen_environment():
        try:
            upsert_screen("Broken", "broken", "wall-tablet", ["weather"], module_layout={"weather": "giant"})
        except ValueError as exc:
            assert "module size" in str(exc)
        else:
            raise AssertionError("invalid module size accepted")


def test_wall_page_applies_configured_module_size_css():
    with screen_environment():
        upsert_screen(
            "Stuen",
            "stuen",
            "wall-tablet",
            ["calendar", "weather"],
            module_layout={"calendar": "full", "weather": "small"},
        )
        page = render_wall_page({"role": "adult"}, "stuen")
        assert 'data-wall-screen-slug="stuen"' in page
        assert '[data-family-card="meal"]{display:none!important}' in page
        assert 'body[data-wall-dashboard="true"] .calendar-card{grid-column:1 / -1;min-height:340px}' in page
        assert 'body[data-wall-dashboard="true"] .weather-card{grid-column:span 1;min-height:190px}' in page


if __name__ == "__main__":
    for test in [
        test_screen_registry_persists_module_size_layout,
        test_screen_registry_rejects_invalid_module_size,
        test_wall_page_applies_configured_module_size_css,
    ]:
        test()
    print("Screen module layout tests OK")
