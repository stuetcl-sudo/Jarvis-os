import tempfile
from contextlib import contextmanager
from pathlib import Path

from app import config
from app.family_view import render_family_page
from app.family_visibility import load_visibility_rules, role_can_see, save_visibility_rules


@contextmanager
def visibility_environment():
    previous = config.DB_PATH
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "visibility.db")
        try:
            yield
        finally:
            config.DB_PATH = previous


def test_default_visibility_keeps_existing_family_view_visible():
    with visibility_environment():
        rules = load_visibility_rules(db_path=config.DB_PATH)
        assert rules["owner"]["calendar"] is True
        assert rules["adult"]["meal"] is True
        assert rules["child"]["tasks"] is True
        assert rules["wall_display"]["safety"] is True


def test_owner_visibility_cannot_be_disabled():
    with visibility_environment():
        rules = save_visibility_rules({"owner": {"calendar": False, "meal": False}}, db_path=config.DB_PATH)
        assert all(rules["owner"].values())
        assert role_can_see("owner", "calendar", rules)


def test_visibility_rules_hide_family_cards_for_role():
    with visibility_environment():
        save_visibility_rules(
            {
                "child": {
                    "calendar": False,
                    "weather": True,
                    "meal": False,
                    "tasks": True,
                    "safety": True,
                }
            },
            db_path=config.DB_PATH,
        )
        page = render_family_page({"role": "child", "display_name": "Barn"})
        assert 'body[data-family-role="child"] [data-family-card="calendar"]{display:none!important}' in page
        assert 'body[data-family-role="child"] [data-family-card="meal"]{display:none!important}' in page
        assert '[data-family-card="weather"]{display:none!important}' not in page


def test_wall_visibility_can_hide_safety_strip():
    with visibility_environment():
        save_visibility_rules({"wall_display": {"safety": False}}, db_path=config.DB_PATH)
        page = render_family_page({"role": "wall_display"})
        assert 'body[data-family-role="wall_display"] #wallSafetyStrip{display:none!important}' in page


if __name__ == "__main__":
    test_default_visibility_keeps_existing_family_view_visible()
    test_owner_visibility_cannot_be_disabled()
    test_visibility_rules_hide_family_cards_for_role()
    test_wall_visibility_can_hide_safety_strip()
    print("Family visibility tests OK")
