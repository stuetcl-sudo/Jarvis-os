import hashlib
from functools import lru_cache
from pathlib import Path

STATIC_ROOT = Path(__file__).resolve().parent / "static"
WALL_TEMPLATE = STATIC_ROOT / "wall.html"
WALL_ASSETS = (
    STATIC_ROOT / "css" / "wall.css",
    STATIC_ROOT / "css" / "wall-details.css",
    STATIC_ROOT / "js" / "wall.js",
    STATIC_ROOT / "js" / "wall-calendar.js",
)
WALL_ASSET_VERSION_PLACEHOLDER = "__WALL_ASSET_VERSION__"
WALL_ROLES = {"owner", "adult", "child", "wall_display"}


@lru_cache(maxsize=1)
def wall_asset_version():
    digest = hashlib.sha256()
    for path in WALL_ASSETS:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def render_wall_page(current_user):
    role = current_user.get("role") if isinstance(current_user, dict) else None
    if role not in WALL_ROLES:
        raise ValueError("wall role required")

    page = WALL_TEMPLATE.read_text(encoding="utf-8")
    mission_link = (
        '<a class="wall-menu-link" href="/admin">Mission Control</a>'
        if role == "owner"
        else ""
    )
    page = page.replace("<!-- WALL_MISSION_LINK -->", mission_link, 1)
    page = page.replace('data-wall-role="wall_display"', f'data-wall-role="{role}"', 1)
    page = page.replace(WALL_ASSET_VERSION_PLACEHOLDER, wall_asset_version())
    return page
