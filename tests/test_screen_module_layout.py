import tempfile
from contextlib import contextmanager
from pathlib import Path

from app import config
from app.screen_registry import SCREEN_TYPES, get_screen, list_screens, normalize_screen_type, upsert_screen
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
        assert wall["wall_user_id"] is None


def test_screen_registry_persists_module_size_layout_and_display_options():
    with screen_environment():
        created = upsert_screen(
            "Stuen",
            "stuen",
            "wall-tablet",
            ["calendar", "weather", "meal"],
            module_layout={"calendar": "full", "weather": "small", "meal": "medium"},
            display_options={"show_admin_link": True, "show_safety_status": False},
            wall_user_id="wall-user-stuen",
        )
        assert created["module_layout"] == {"calendar": "full", "weather": "small", "meal": "medium"}
        assert created["display_options"] == {"show_admin_link": True, "show_safety_status": False}

        reloaded = get_screen("stuen")
        assert reloaded["module_layout"] == created["module_layout"]
        assert reloaded["display_options"] == created["display_options"]
        assert reloaded["modules"] == ["calendar", "weather", "meal"]
        assert reloaded["wall_user_id"] == "wall-user-stuen"


def test_multiple_screen_profiles_coexist_with_independent_modules():
    with screen_environment():
        kitchen = upsert_screen("Køkken", "koekken", "wall-ipad", ["calendar", "meal", "tasks"])
        hallway = upsert_screen("Entré", "entre", "wall-surface", ["routine", "weather", "home"])
        screens = {screen["slug"]: screen for screen in list_screens()}
        assert {"wall", "koekken", "entre"}.issubset(screens)
        assert kitchen["modules"] == ["calendar", "meal", "tasks"]
        assert hallway["modules"] == ["routine", "weather", "home"]
        assert kitchen["url"] == "/wall/koekken"
        assert hallway["url"] == "/wall/entre"

        kitchen_page = render_wall_page({"role": "owner"}, "koekken")
        hallway_page = render_wall_page({"role": "owner"}, "entre")
        assert '[data-family-card="routine"]{display:none!important}' in kitchen_page
        assert '[data-family-card="weather"]{display:none!important}' in kitchen_page
        assert '[data-family-card="calendar"]{display:none!important}' in hallway_page
        assert '[data-family-card="meal"]{display:none!important}' in hallway_page
        assert '[data-family-card="tasks"]{display:none!important}' in hallway_page
        assert '[data-family-card="home"]{display:none!important}' not in hallway_page


def test_all_supported_screen_types_normalize_without_device_detection():
    assert SCREEN_TYPES == {"wall-large", "wall-surface", "wall-ipad", "wall-tablet", "wall-square", "mobile"}
    for screen_type in SCREEN_TYPES:
        assert normalize_screen_type(f" {screen_type.upper()} ") == screen_type
    try:
        normalize_screen_type("surface-pro-9")
    except ValueError:
        pass
    else:
        raise AssertionError("device-specific screen type accepted")


def test_wall_screen_binding_isolated_between_wall_users():
    with screen_environment():
        upsert_screen(
            "Wall 1",
            "wall-1",
            "wall-surface",
            ["weather"],
            wall_user_id="wall-user-1",
        )
        upsert_screen(
            "Wall 2",
            "wall-2",
            "wall-tablet",
            ["calendar"],
            wall_user_id="wall-user-2",
        )

        first = render_wall_page(
            {
                "user_id": "wall-user-1",
                "role": "wall_display",
            },
            "wall-1",
        )
        assert 'data-wall-screen-name="Wall 1"' in first

        try:
            render_wall_page(
                {
                    "user_id": "wall-user-1",
                    "role": "wall_display",
                },
                "wall-2",
            )
        except PermissionError:
            pass
        else:
            raise AssertionError("Wall user could open another assigned screen")

        owner = render_wall_page(
            {
                "user_id": "owner-1",
                "role": "owner",
            },
            "wall-2",
        )
        assert 'data-wall-screen-name="Wall 2"' in owner



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
        test_multiple_screen_profiles_coexist_with_independent_modules,
        test_all_supported_screen_types_normalize_without_device_detection,
        test_wall_screen_binding_isolated_between_wall_users,
        test_screen_registry_rejects_invalid_module_size,
        test_wall_page_applies_configured_module_size_css_and_status_badge,
    ]:
        test()
    print("Screen module layout tests OK")
