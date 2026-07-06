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
# The wall grid uses 12 columns on wide screens. Smaller breakpoints use
# 8, 4, 2 and finally 1 column, so generated layout rules must scale down.
MODULE_SIZE_STYLES = {
    "wide": {
        "small": "grid-column:span 3;min-height:190px",
        "medium": "grid-column:span 4",
        "large": "grid-column:span 6;min-height:320px",
        "wide": "grid-column:span 8",
        "full": "grid-column:1 / -1;min-height:340px",
    },
    "desktop": {
        "small": "grid-column:span 2;min-height:190px",
        "medium": "grid-column:span 3",
        "large": "grid-column:span 4;min-height:300px",
        "wide": "grid-column:span 6",
        "full": "grid-column:1 / -1;min-height:320px",
    },
    "tablet": {
        "small": "grid-column:span 1;min-height:180px",
        "medium": "grid-column:span 2",
        "large": "grid-column:span 2;min-height:280px",
        "wide": "grid-column:1 / -1",
        "full": "grid-column:1 / -1;min-height:300px",
    },
}
WALL_STATUS_STYLE = """
body[data-wall-dashboard=\"true\"] .family-grid{align-items:stretch}
body[data-wall-dashboard=\"true\"] .family-card{height:100%}
.wall-home-status{min-height:44px;display:inline-flex;align-items:center;gap:8px;padding:9px 14px;border:1px solid var(--card-border);border-radius:14px;background:var(--soft);color:var(--text);font-weight:820;letter-spacing:.04em}
.wall-home-status-dot{width:13px;height:13px;border-radius:999px;background:var(--muted);box-shadow:0 0 0 6px var(--soft)}
.wall-home-status.ok .wall-home-status-dot{background:var(--good)}
.wall-home-status.warning .wall-home-status-dot{background:var(--warning)}
.wall-home-status.critical .wall-home-status-dot{background:var(--critical)}
.wall-home-status.unknown .wall-home-status-dot{background:var(--muted)}
@media(max-width:640px){.wall-home-status{grid-column:1 / -1;justify-content:center}}
""".strip()
SURFACE_WALL_STYLE = """
@media (orientation: landscape) and (min-width:1000px) and (max-width:1400px) and (min-aspect-ratio:4/3) and (max-aspect-ratio:17/10){
body[data-wall-dashboard=\"true\"] .family-shell{width:min(100% - 22px,1220px);padding-top:max(12px,env(safe-area-inset-top))}
body[data-wall-dashboard=\"true\"] .family-header{min-height:0;padding-bottom:10px}
body[data-wall-dashboard=\"true\"] .family-header h1{font-size:clamp(36px,4.2vw,54px)}
body[data-wall-dashboard=\"true\"] .family-clock{font-size:clamp(40px,5vw,64px)}
body[data-wall-dashboard=\"true\"] .family-grid{grid-template-columns:repeat(4,minmax(0,1fr));align-items:start;gap:10px}
body[data-wall-dashboard=\"true\"] .routine-card,body[data-wall-dashboard=\"true\"] .weather-card{grid-column:span 2!important;min-height:280px!important;height:auto}
body[data-wall-dashboard=\"true\"] .calendar-card,body[data-wall-dashboard=\"true\"] .meal-card,body[data-wall-dashboard=\"true\"] .family-tasks-card{grid-column:span 2!important;min-height:0!important;height:auto}
body[data-wall-dashboard=\"true\"] .routine-card{order:1}
body[data-wall-dashboard=\"true\"] .weather-card{order:2}
body[data-wall-dashboard=\"true\"] .calendar-card{order:3}
body[data-wall-dashboard=\"true\"] .meal-card{order:4}
body[data-wall-dashboard=\"true\"] .family-tasks-card{order:5}
body[data-wall-dashboard=\"true\"] .routine-pictogram-frame{min-height:54px;max-height:66px}
body[data-wall-dashboard=\"true\"] .routine-pictogram{width:46px;height:46px;max-width:46px;max-height:46px}
body[data-wall-dashboard=\"true\"] .routine-title{font-size:clamp(28px,3vw,40px);line-height:1.05;word-break:normal;overflow-wrap:break-word}
body[data-wall-dashboard=\"true\"] .weather-temperature{font-size:clamp(44px,5vw,60px)}
body[data-wall-dashboard=\"true\"] .weather-forecast-item{min-height:74px}
body[data-wall-dashboard=\"true\"] .wall-safety-strip{position:static!important;margin-top:10px}
body.wall-is-fullscreen[data-wall-dashboard=\"true\"] .family-shell{width:min(100% - 64px,1180px);padding-top:18px;padding-bottom:18px}
body.wall-is-fullscreen[data-wall-dashboard=\"true\"] .family-header{padding-bottom:12px}
body.wall-is-fullscreen[data-wall-dashboard=\"true\"] .family-header h1{font-size:clamp(34px,4vw,50px)}
body.wall-is-fullscreen[data-wall-dashboard=\"true\"] .family-clock{font-size:clamp(38px,4.6vw,58px)}
body.wall-is-fullscreen[data-wall-dashboard=\"true\"] .family-grid{gap:12px;align-items:start}
body.wall-is-fullscreen[data-wall-dashboard=\"true\"] .routine-card,body.wall-is-fullscreen[data-wall-dashboard=\"true\"] .weather-card{min-height:270px!important}
body.wall-is-fullscreen[data-wall-dashboard=\"true\"] .weather-temperature{font-size:clamp(42px,4.6vw,56px)}
body.wall-is-fullscreen[data-wall-dashboard=\"true\"] .wall-display-actions a,body.wall-is-fullscreen[data-wall-dashboard=\"true\"] .wall-display-actions button{min-height:40px;padding:7px 12px}
}
""".strip()


def screen_option(screen, key, default=False):
    options = screen.get("display_options") if isinstance(screen, dict) else {}
    return bool(options.get(key, default)) if isinstance(options, dict) else default


def wall_actions_for(role, screen):
    links = [
        '<div class="wall-home-status unknown" id="wallHomeStatusBadge" role="status" aria-live="polite"><span class="wall-home-status-dot" id="wallHomeStatusDot" aria-hidden="true"></span><span id="wallHomeStatusText">Status hentes…</span></div>',
        '<button type="button" id="wallFullscreen">Fuld skærm</button>',
        '<a href="/">Familie</a>',
    ]
    if role == "owner" and screen_option(screen, "show_admin_link", False):
        links.append('<a href="/admin">Administration</a>')
    return '<nav class="wall-display-actions" aria-label="Vægskærm">' + "".join(links) + "</nav>"


def module_visibility_style(screen):
    modules = set(screen.get("modules") or [])
    hidden = ['body[data-wall-dashboard="true"] [data-family-card="home"]{display:none!important}']
    for module in ["routine", "calendar", "weather", "meal", "tasks", "system"]:
        if module not in modules:
            hidden.append(f'body[data-wall-dashboard="true"] [data-family-card="{module}"]{{display:none!important}}')
    if not screen_option(screen, "show_safety_status", True):
        hidden.append('body[data-wall-dashboard="true"] #wallSafetyStrip{display:none!important}')
    return "".join(hidden)


def module_layout_rules(screen, breakpoint):
    rules = []
    modules = set(screen.get("modules") or [])
    layout = screen.get("module_layout") or {}
    styles = MODULE_SIZE_STYLES[breakpoint]
    for module in ["routine", "calendar", "weather", "meal", "tasks", "system"]:
        if module not in modules:
            continue
        selector = MODULE_CARD_SELECTORS.get(module)
        css = styles.get(layout.get(module))
        if selector and css:
            rules.append(f'body[data-wall-dashboard="true"] {selector}{{{css}}}')
    return "".join(rules)


def module_layout_style(screen):
    wide = module_layout_rules(screen, "wide")
    desktop = module_layout_rules(screen, "desktop")
    tablet = module_layout_rules(screen, "tablet")
    return (
        "@media(min-width:1280px){"
        + wide
        + "}"
        + "@media(min-width:1181px) and (max-width:1279px){"
        + desktop
        + "}"
        + "@media(min-width:921px) and (max-width:1180px){"
        + tablet
        + "}"
    )


def screen_style(screen):
    css = WALL_STATUS_STYLE + module_visibility_style(screen) + module_layout_style(screen) + SURFACE_WALL_STYLE
    return "<style>" + css + "</style>" if css else ""


def render_wall_page(current_user, screen_slug="wall"):
    role = current_user.get("role") if isinstance(current_user, dict) else None
    if role not in WALL_ROLES:
        raise ValueError("wall role required")

    screen = get_screen(screen_slug or "wall")
    if not screen or not screen.get("is_active"):
        raise LookupError("screen not found")

    shared_display = {"role": "wall_display", "display_name": ""}
    page = render_family_page(shared_display, wall_actions=wall_actions_for(role, screen))
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
