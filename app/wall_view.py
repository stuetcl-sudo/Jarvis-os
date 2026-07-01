from pathlib import Path

WALL_TEMPLATE = Path(__file__).resolve().parent / "static" / "wall.html"
WALL_ROLES = {"owner", "adult", "child", "wall_display"}


def render_wall_page(current_user):
    role = current_user.get("role") if isinstance(current_user, dict) else None
    if role not in WALL_ROLES:
        raise ValueError("wall role required")
    page = WALL_TEMPLATE.read_text(encoding="utf-8")
    mission_link = '<a class="wall-menu-link" href="/admin">Mission Control</a>' if role == "owner" else ""
    page = page.replace("<!-- WALL_MISSION_LINK -->", mission_link, 1)
    page = page.replace('data-wall-role="wall_display"', f'data-wall-role="{role}"', 1)
    return page
