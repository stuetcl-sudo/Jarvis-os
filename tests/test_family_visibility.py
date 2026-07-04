import tempfile
from contextlib import contextmanager
from pathlib import Path

from app import config
from app.family_view import render_family_page
from app.family_visibility import (
    load_action_rules,
    load_visibility_rules,
    role_can_do,
    role_can_see,
    save_action_rules,
    save_visibility_rules,
)


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


def test_default_action_permissions_are_family_safe():
    with visibility_environment():
        rules = load_action_rules(db_path=config.DB_PATH)
        assert rules["owner"]["task_add"] is True
        assert rules["adult"]["task_remove"] is True
        assert rules["child"]["task_complete"] is True
        assert rules["child"]["task_add"] is False
        assert rules["wall_display"]["task_complete"] is False


def test_owner_visibility_and_actions_cannot_be_disabled():
    with visibility_environment():
        visibility = save_visibility_rules({"owner": {"calendar": False, "meal": False}}, db_path=config.DB_PATH)
        actions = save_action_rules({"owner": {"task_add": False, "task_remove": False}}, db_path=config.DB_PATH)
        assert all(visibility["owner"].values())
        assert all(actions["owner"].values())
        assert role_can_see("owner", "calendar", visibility)
        assert role_can_do("owner", "task_add", actions)


def test_child_can_be_allowed_to_add_family_tasks():
    with visibility_environment():
        rules = save_action_rules({"child": {"task_add": True}}, db_path=config.DB_PATH)
        assert role_can_do("child", "task_add", rules)
        assert not role_can_do("child", "task_remove", rules)


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
    test_default_action_permissions_are_family_safe()
    test_owner_visibility_and_actions_cannot_be_disabled()
    test_child_can_be_allowed_to_add_family_tasks()
    test_visibility_rules_hide_family_cards_for_role()
    test_wall_visibility_can_hide_safety_strip()
    print("Family visibility tests OK")
