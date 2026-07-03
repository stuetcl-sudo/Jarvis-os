from html import escape

from app.family_view import render_family_page
from app.screen_registry import get_screen

WALL_ROLES = {"owner", "adult", "child", "wall_display"}


def wall_actions_for(role):
    links = [
        '<button type="button" id="wallFullscreen">Fuld skærm</button>',
        '<a href="/">Familie</a>',
    ]
    if role == "owner":
        links.append('<a href="/admin">Administration</a>')
    return '<nav class="wall-display-actions" aria-label="Vægskærm">' + "".join(links) + "</nav>"


def module_visibility_style(screen):
    modules = set(screen.get("modules") or [])
    hidden = []
    for module in ["routine", "calendar", "weather", "meal", "tasks", "home", "system"]:
        if module not in modules:
            hidden.append(f'body[data-wall-dashboard="true"] [data-family-card="{module}"]{{display:none!important}}')
    return "<style>" + "".join(hidden) + "</style>" if hidden else ""


def render_wall_page(current_user, screen_slug="wall"):
    role = current_user.get("role") if isinstance(current_user, dict) else None
    if role not in WALL_ROLES:
        raise ValueError("wall role required")

    screen = get_screen(screen_slug or "wall")
    if not screen or not screen.get("is_active"):
        raise LookupError("screen not found")

    shared_display = {"role": "wall_display", "display_name": ""}
    page = render_family_page(shared_display, wall_actions=wall_actions_for(role))
    safe_name = escape(screen["name"])
    safe_slug = escape(screen["slug"])
    safe_type = escape(screen["screen_type"])
    page = page.replace("<title>Jarvis – Hjem</title>", f"<title>Jarvis – {safe_name}</title>", 1)
    page = page.replace("</head>", module_visibility_style(screen) + "\n</head>", 1)
    page = page.replace(
        "<body ",
        f'<body data-wall-dashboard="true" data-wall-actor-role="{role}" data-wall-screen-slug="{safe_slug}" data-wall-screen-name="{safe_name}" data-wall-preferred-profile="{safe_type}" ',
        1,
    )
    return page
