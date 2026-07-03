from html import escape

from app.family_view import render_family_page
from app.screen_registry import get_screen

WALL_ROLES = {"owner", "adult", "child", "wall_display"}
MODULE_CARD_SELECTORS = {
    "routine": ".routine-card",
    "calendar": ".calendar-card",
    "weather": ".weather-card",
    "meal": ".meal-card",
    "tasks": ".family-tasks-card",
    "home": ".home-card",
    "system": ".system-card",
}
# The wall grid uses 12 columns on wide screens. A user-facing module size
# must therefore map to useful spans, not raw CSS span 1/2 values.
MODULE_SIZE_STYLES = {
    "small": "grid-column:span 3;min-height:190px",
    "medium": "grid-column:span 4",
    "large": "grid-column:span 6;min-height:320px",
    "wide": "grid-column:span 8",
    "full": "grid-column:1 / -1;min-height:340px",
}


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
    return "".join(hidden)


def module_layout_style(screen):
    rules = []
    modules = set(screen.get("modules") or [])
    layout = screen.get("module_layout") or {}
    for module in ["routine", "calendar", "weather", "meal", "tasks", "home", "system"]:
        if module not in modules:
            continue
        selector = MODULE_CARD_SELECTORS.get(module)
        css = MODULE_SIZE_STYLES.get(layout.get(module))
        if selector and css:
            rules.append(f'body[data-wall-dashboard="true"] {selector}{{{css}}}')
    return "".join(rules)


def screen_style(screen):
    css = module_visibility_style(screen) + module_layout_style(screen)
    return "<style>" + css + "</style>" if css else ""


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
    page = page.replace("</head>", screen_style(screen) + "\n</head>", 1)
    page = page.replace(
        "<body ",
        f'<body data-wall-dashboard="true" data-wall-actor-role="{role}" data-wall-screen-slug="{safe_slug}" data-wall-screen-name="{safe_name}" data-wall-preferred-profile="{safe_type}" ',
        1,
    )
    return page
