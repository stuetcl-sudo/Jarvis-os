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
body[data-wall-dashboard=\"true\"]{color-scheme:dark;--bg:#07111f;--surface:rgba(15,23,42,.88);--soft:rgba(148,163,184,.08);--card-border:rgba(148,163,184,.24);--text:#eef4fb;--muted:#aab8c9;--accent:#7dd3fc;--good:#86efac;--warning:#fde68a;--critical:#fecaca;background:radial-gradient(circle at top right,#17324f,var(--bg) 48%);color:var(--text)}
body[data-wall-dashboard=\"true\"] .family-shell{color:var(--text);overflow-x:hidden}
body[data-wall-dashboard=\"true\"] .family-grid{align-items:stretch}
body[data-wall-dashboard=\"true\"] .family-card{height:100%;background:var(--surface);border-color:var(--card-border);box-shadow:0 18px 52px rgba(0,0,0,.22)}
body[data-wall-dashboard=\"true\"] .family-view-label{display:none!important}
body[data-wall-dashboard=\"true\"] .wall-top-bars{display:grid;grid-template-columns:1fr auto;align-items:center;gap:14px;margin:0 0 10px 0}
body[data-wall-dashboard=\"true\"] .wall-top-bars .wall-safety-strip,body[data-wall-dashboard=\"true\"] .wall-top-bars .wall-display-actions{min-height:44px;display:flex;align-items:center;margin:0!important}
body[data-wall-dashboard=\"true\"] .wall-top-bars .wall-safety-strip{position:static!important;z-index:1;flex-wrap:wrap;gap:8px}
body[data-wall-dashboard=\"true\"] .wall-top-bars .wall-display-actions{justify-content:flex-end;gap:8px;white-space:nowrap}
body[data-wall-dashboard=\"true\"] .wall-top-bars button,body[data-wall-dashboard=\"true\"] .wall-top-bars a{background:rgba(148,163,184,.16);border:1px solid var(--card-border);color:var(--text)}
.wall-home-status{min-height:44px;display:inline-flex;align-items:center;gap:8px;padding:9px 14px;border:1px solid var(--card-border);border-radius:14px;background:var(--soft);color:var(--text);font-weight:820;letter-spacing:.04em}
.wall-home-status-dot{width:13px;height:13px;border-radius:999px;background:var(--muted);box-shadow:0 0 0 6px var(--soft)}
.wall-home-status.ok .wall-home-status-dot{background:var(--good)}
.wall-home-status.warning .wall-home-status-dot{background:var(--warning)}
.wall-home-status.critical .wall-home-status-dot{background:var(--critical)}
.wall-home-status.unknown .wall-home-status-dot{background:var(--muted)}
@media(max-width:640px){.wall-home-status{grid-column:1 / -1;justify-content:center}}
""".strip()
SURFACE_WALL_STYLE = """
@media (orientation: landscape) and (min-width:1280px) and (max-width:1450px) and (min-height:840px) and (max-height:980px){
body[data-wall-dashboard=\"true\"] .family-shell{width:min(100% - 24px,1180px);padding-top:max(6px,env(safe-area-inset-top))}
body[data-wall-dashboard=\"true\"] .family-header{min-height:0;padding-bottom:6px}
body[data-wall-dashboard=\"true\"] .family-header h1{font-size:clamp(32px,3.8vw,46px)}
body[data-wall-dashboard=\"true\"] .family-clock{font-size:clamp(36px,4.4vw,56px)}
body[data-wall-dashboard=\"true\"] .wall-top-bars{margin-bottom:10px;gap:10px}
body[data-wall-dashboard=\"true\"] .family-grid{grid-template-columns:repeat(4,minmax(0,1fr));align-items:start;gap:10px;overflow:hidden}
body[data-wall-dashboard=\"true\"] .routine-card,body[data-wall-dashboard=\"true\"] .weather-card{grid-column:span 2!important;min-height:300px!important;height:clamp(340px,38vh,365px)!important;padding:16px!important;overflow:hidden}
body[data-wall-dashboard=\"true\"].wall-is-fullscreen .routine-card,body[data-wall-dashboard=\"true\"].wall-is-fullscreen .weather-card{height:clamp(368px,41vh,394px)!important;margin-top:20px!important;overflow:visible!important}
body[data-wall-dashboard=\"true\"] .calendar-card,body[data-wall-dashboard=\"true\"] .meal-card,body[data-wall-dashboard=\"true\"] .family-tasks-card{grid-column:span 2!important;min-height:0!important;height:auto!important;overflow:hidden}
body[data-wall-dashboard=\"true\"] .routine-card{order:1;padding-top:12px!important}
body[data-wall-dashboard=\"true\"] .weather-card{order:2}
body[data-wall-dashboard=\"true\"] .calendar-card{order:3}
body[data-wall-dashboard=\"true\"] .meal-card{order:4}
body[data-wall-dashboard=\"true\"] .family-tasks-card{order:5}
body[data-wall-dashboard=\"true\"] .routine-panel{margin-top:6px;gap:8px;align-items:stretch;grid-template-columns:minmax(175px,.74fr) minmax(0,1fr);height:calc(100% - 78px);min-height:0;overflow:hidden}
body[data-wall-dashboard=\"true\"] .routine-copy{display:flex;flex-direction:column;margin-top:-10px;min-width:0;min-height:0;height:100%;overflow:hidden}
body[data-wall-dashboard=\"true\"] .routine-pictogram-frame{width:158px;max-width:158px;min-height:104px;max-height:104px;justify-self:center;border-radius:24px;cursor:pointer;transition:transform .12s ease,box-shadow .12s ease}
body[data-wall-dashboard=\"true\"] .routine-pictogram-frame:active{transform:scale(.98)}
body[data-wall-dashboard=\"true\"] .routine-pictogram-frame[aria-disabled=\"true\"]{cursor:default;opacity:.78}
body[data-wall-dashboard=\"true\"] .routine-pictogram{width:50px;height:50px;max-width:50px;max-height:50px}
body[data-wall-dashboard=\"true\"] .routine-title{font-size:clamp(18px,1.75vw,24px);line-height:1.12;word-break:normal;overflow-wrap:break-word;hyphens:auto;max-width:100%;max-height:2.24em;overflow:hidden;display:block;padding-bottom:3px}
body[data-wall-dashboard=\"true\"] .routine-actions{display:grid;grid-template-columns:minmax(82px,.62fr) minmax(0,1fr);margin-top:auto;gap:8px;flex:0 0 auto}
body[data-wall-dashboard=\"true\"] .routine-reset{display:none!important}
body[data-wall-dashboard=\"true\"] .routine-actions button,body[data-wall-dashboard=\"true\"] .routine-edit-action,body[data-wall-dashboard=\"true\"] .routine-switch button{min-height:38px;padding:8px 10px;font-size:14px}
body[data-wall-dashboard=\"true\"] .weather-symbol{width:62px;height:62px;border-radius:18px;font-size:38px}
body[data-wall-dashboard=\"true\"] .weather-temperature{font-size:clamp(42px,4.8vw,56px)}
body[data-wall-dashboard=\"true\"] .weather-data{margin-top:12px}
body[data-wall-dashboard=\"true\"] .weather-forecast{margin-top:12px;gap:8px}
body[data-wall-dashboard=\"true\"] .weather-forecast-item{min-height:62px;padding:8px;border-radius:16px}
body[data-wall-dashboard=\"true\"] .weather-forecast-day,body[data-wall-dashboard=\"true\"] .weather-forecast-temperatures{font-size:14px}
body[data-wall-dashboard=\"true\"] .weather-forecast-symbol{font-size:21px}
body[data-wall-dashboard=\"true\"] .weather-forecast-rain{font-size:12px}
}
""".strip()
PC_WALL_STYLE = """
@media (orientation: landscape) and (min-width:1700px) and (max-width:2200px) and (min-height:820px) and (max-height:1200px) and (max-resolution:1.5dppx){
body[data-wall-dashboard=\"true\"] .family-shell{width:min(100% - 72px,1540px);padding-top:max(10px,env(safe-area-inset-top))}
body[data-wall-dashboard=\"true\"] .family-header{min-height:0;padding-bottom:10px}
body[data-wall-dashboard=\"true\"] .family-header h1{font-size:clamp(48px,3.8vw,68px)}
body[data-wall-dashboard=\"true\"] .family-clock{font-size:clamp(68px,5vw,96px)}
body[data-wall-dashboard=\"true\"] .wall-top-bars{margin-bottom:12px;gap:12px}
body[data-wall-dashboard=\"true\"] .family-grid{grid-template-columns:repeat(4,minmax(0,1fr));align-items:start;gap:14px;overflow:hidden}
body[data-wall-dashboard=\"true\"] .routine-card,body[data-wall-dashboard=\"true\"] .weather-card{grid-column:span 2!important;min-height:300px!important;height:clamp(430px,46vh,470px)!important;padding:20px!important;overflow:hidden}
body[data-wall-dashboard=\"true\"] .calendar-card,body[data-wall-dashboard=\"true\"] .meal-card,body[data-wall-dashboard=\"true\"] .family-tasks-card{grid-column:span 2!important;min-height:0!important;height:auto!important;overflow:hidden}
body[data-wall-dashboard=\"true\"] .routine-card{order:1;padding-top:16px!important}
body[data-wall-dashboard=\"true\"] .weather-card{order:2}
body[data-wall-dashboard=\"true\"] .calendar-card{order:3}
body[data-wall-dashboard=\"true\"] .meal-card{order:4}
body[data-wall-dashboard=\"true\"] .family-tasks-card{order:5}
body[data-wall-dashboard=\"true\"] .routine-panel{margin-top:6px;gap:18px;align-items:center;grid-template-columns:230px minmax(0,1fr);min-height:0;height:calc(100% - 70px);overflow:visible}
body[data-wall-dashboard=\"true\"] .routine-copy{display:flex;flex-direction:column;gap:5px;margin-top:0;min-width:0;min-height:0;height:100%;overflow:visible}
body[data-wall-dashboard=\"true\"] .routine-pictogram-frame{width:220px;max-width:220px;min-height:128px;max-height:128px;justify-self:center;align-self:center;border-radius:26px;cursor:pointer}
body[data-wall-dashboard=\"true\"] .routine-pictogram{width:62px;height:62px;max-width:62px;max-height:62px}
body[data-wall-dashboard=\"true\"] .routine-title{font-size:clamp(24px,1.8vw,34px);line-height:1.06;word-break:normal;overflow-wrap:break-word;hyphens:auto;max-width:100%;max-height:none;overflow:visible;display:block;padding-bottom:0}
body[data-wall-dashboard=\"true\"] .routine-actions{display:flex;gap:10px;align-items:center;justify-content:flex-start;margin-top:auto;flex:0 0 auto}
body[data-wall-dashboard=\"true\"] .routine-reset{display:none!important}
body[data-wall-dashboard=\"true\"] #routineBack{display:inline-flex!important;width:auto!important;min-width:104px;max-width:118px;flex:0 0 auto}
body[data-wall-dashboard=\"true\"] #routineComplete{display:inline-flex!important;width:auto!important;min-width:128px;max-width:145px;flex:0 0 auto}
body[data-wall-dashboard=\"true\"] .routine-actions button,body[data-wall-dashboard=\"true\"] .routine-edit-action,body[data-wall-dashboard=\"true\"] .routine-switch button{min-height:34px;padding:7px 12px;font-size:14px}
body[data-wall-dashboard=\"true\"] .weather-symbol{width:76px;height:76px;border-radius:22px;font-size:44px}
body[data-wall-dashboard=\"true\"] .weather-temperature{font-size:clamp(48px,4vw,68px)}
body[data-wall-dashboard=\"true\"] .weather-data{margin-top:14px}
body[data-wall-dashboard=\"true\"] .weather-forecast{margin-top:14px;gap:10px}
body[data-wall-dashboard=\"true\"] .weather-forecast-item{min-height:78px;padding:10px;border-radius:18px}
body[data-wall-dashboard=\"true\"] .weather-forecast-day,body[data-wall-dashboard=\"true\"] .weather-forecast-temperatures{font-size:15px}
body[data-wall-dashboard=\"true\"] .weather-forecast-symbol{font-size:24px}
body[data-wall-dashboard=\"true\"] .weather-forecast-rain{font-size:12px}
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
    hidden = []
    for module in ["routine", "calendar", "weather", "meal", "tasks", "home", "system"]:
        if module == "home" and screen.get("slug") == "wall":
            hidden.append('body[data-wall-dashboard="true"] [data-family-card="home"]{display:none!important}')
            continue
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
    for module in ["routine", "calendar", "weather", "meal", "tasks", "home", "system"]:
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
    css = WALL_STATUS_STYLE + module_visibility_style(screen) + module_layout_style(screen) + SURFACE_WALL_STYLE + PC_WALL_STYLE
    return "<style>" + css + "</style>" if css else ""


def extract_html_block(page, start_marker, end_marker):
    start = page.find(start_marker)
    if start == -1:
        return page, ""
    end = page.find(end_marker, start)
    if end == -1:
        return page, ""
    end += len(end_marker)
    block = page[start:end]
    return page[:start] + page[end:], block


def move_wall_top_bars_above_cards(page):
    page, strip = extract_html_block(page, '<section class="wall-safety-strip"', "</section>")
    page, actions = extract_html_block(page, '<nav class="wall-display-actions"', "</nav>")
    if not strip and not actions:
        return page
    top_bars = '<div class="wall-top-bars">' + strip + actions + "</div>"
    grid_start = page.find('<section class="family-grid"')
    if grid_start == -1:
        return page + top_bars
    return page[:grid_start] + top_bars + "\n\n" + page[grid_start:]


def render_wall_page(current_user, screen_slug="wall"):
    role = current_user.get("role") if isinstance(current_user, dict) else None
    if role not in WALL_ROLES:
        raise ValueError("wall role required")

    screen = get_screen(screen_slug or "wall")
    if not screen or not screen.get("is_active"):
        raise LookupError("screen not found")

    assigned_user_id = screen.get("wall_user_id")
    if (
        role == "wall_display"
        and assigned_user_id
        and current_user.get("user_id") != assigned_user_id
    ):
        raise PermissionError("wall screen is assigned to another user")

    shared_display = {"role": "wall_display", "display_name": ""}
    page = render_family_page(shared_display, wall_actions=wall_actions_for(role, screen))
    page = move_wall_top_bars_above_cards(page)
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
