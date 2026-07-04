from html import escape
from pathlib import Path

from app.family_visibility import load_visibility_rules, role_can_see

FAMILY_TEMPLATE = Path(__file__).resolve().parent / "static" / "index.html"
FAMILY_ROLES = {"owner", "adult", "child", "wall_display"}
PERSONALIZED_ROLES = {"owner", "adult", "child"}
ROLE_COPY = {
    "anonymous": ("Fælles overblik", "Her er et roligt overblik over hjemmet."),
    "owner": ("Familiens overblik", "Her er både familiens overblik og den tekniske status."),
    "adult": ("Familiens dag", "Her er dagens fælles information samlet roligt og enkelt."),
    "child": ("Din dag", "Her kan du se dagens aftaler, vejr, madplan og opgaver."),
    "wall_display": ("Fælles husholdningsskærm", "Dagens fælles information til hele hjemmet."),
}

TECHNICAL_STATUS = """
    <section class="status-strip" data-family-section="technical-status" aria-label="Teknisk status for Jarvis">
      <article class="status-tile" id="jarvisStatusCard">
        <span class="status-dot neutral" id="jarvisStatusDot" aria-hidden="true"></span>
        <div>
          <span class="tile-label">Jarvis</span>
          <strong id="jarvisStatus">Forbinder…</strong>
        </div>
      </article>
      <article class="status-tile">
        <span class="tile-label">Sikker tilstand</span>
        <strong id="safeMode">–</strong>
      </article>
      <article class="status-tile">
        <span class="tile-label">Docker-systemer online</span>
        <strong id="systemsOnline">–</strong>
      </article>
      <article class="status-tile">
        <span class="tile-label">Aktive hændelser</span>
        <strong id="incidentCount">–</strong>
      </article>
    </section>
"""

HOME_CARD = """
      <article class="family-card home-card" data-family-card="home">
        <div class="card-icon" aria-hidden="true">🏠</div>
        <div class="card-heading"><p class="card-eyebrow">Hjemmet</p><h2>Roligt overblik</h2></div>
        <dl class="home-status-list">
          <div><dt>Overordnet status</dt><dd id="overallHomeStatus">Kontrollerer…</dd></div>
          <div><dt>Senest opdateret</dt><dd id="lastUpdated">–</dd></div>
        </dl>
      </article>
"""

TECHNICAL_CARD = """
      <article class="family-card system-card" data-family-card="technical" data-family-section="technical-system">
        <div class="card-icon" aria-hidden="true">⚙️</div>
        <div class="card-heading"><p class="card-eyebrow">System</p><h2>Jarvis-os</h2></div>
        <dl class="system-metrics">
          <div><dt>CPU</dt><dd id="cpuMetric">–</dd></div>
          <div><dt>Hukommelse</dt><dd id="memoryMetric">–</dd></div>
          <div><dt>Disk</dt><dd id="diskMetric">–</dd></div>
        </dl>
      </article>
"""

ROUTINE_EDITOR_ACTION = """
          <button type="button" class="routine-edit-action" id="routineEditButton">Rediger rutine</button>
"""

VISIBILITY_SELECTORS = {
    "calendar": '[data-family-card="calendar"]',
    "weather": '[data-family-card="weather"]',
    "meal": '[data-family-card="meal"]',
    "tasks": '[data-family-card="tasks"]',
    "safety": "#wallSafetyStrip",
}


def anonymous_context():
    return {
        "role": "anonymous",
        "display_name": "",
        "view": "anonymous",
        "kiosk": "false",
        "label": ROLE_COPY["anonymous"][0],
        "subtitle": ROLE_COPY["anonymous"][1],
    }


def resolve_family_context(current_user):
    if not isinstance(current_user, dict):
        return anonymous_context()
    role = current_user.get("role")
    if role not in FAMILY_ROLES:
        return anonymous_context()
    display_name = str(current_user.get("display_name") or "").strip() if role in PERSONALIZED_ROLES else ""
    view = "shared-display" if role == "wall_display" else role
    return {
        "role": role,
        "display_name": display_name,
        "view": view,
        "kiosk": "true" if role == "wall_display" else "false",
        "label": ROLE_COPY[role][0],
        "subtitle": ROLE_COPY[role][1],
    }


def navigation_for(role):
    if role == "anonymous":
        return '<nav class="family-navigation" aria-label="Bruger"><a class="family-nav-link subtle" href="/login">Log ind</a></nav>'
    links = ['<a class="family-nav-link subtle" href="/login">Skift bruger</a>']
    if role == "owner":
        links.append('<a class="family-nav-link primary" href="/admin">Mission Control</a>')
    return '<nav class="family-navigation" aria-label="Bruger">' + "".join(links) + "</nav>"


def visibility_style(role):
    if role == "anonymous":
        return ""
    rules = load_visibility_rules()
    hidden = []
    for feature, selector in VISIBILITY_SELECTORS.items():
        if not role_can_see(role, feature, rules):
            hidden.append(f'body[data-family-role="{role}"] {selector}{{display:none!important}}')
    return "<style>" + "".join(hidden) + "</style>" if hidden else ""


def render_family_page(current_user, wall_actions=""):
    context = resolve_family_context(current_user)
    page = FAMILY_TEMPLATE.read_text(encoding="utf-8")
    body = (
        f'<body data-family-role="{context["role"]}" '
        f'data-family-display-name="{escape(context["display_name"], quote=True)}" '
        f'data-family-view="{context["view"]}" data-family-kiosk="{context["kiosk"]}" '
        f'data-family-label="{escape(context["label"], quote=True)}" '
        f'data-family-subtitle="{escape(context["subtitle"], quote=True)}">'
    )
    page = page.replace(
        '<body data-family-role="anonymous" data-family-display-name="" data-family-view="anonymous" data-family-kiosk="false" data-family-label="Fælles overblik" data-family-subtitle="Her er et roligt overblik over hjemmet.">',
        body,
        1,
    )
    page = page.replace("</head>", visibility_style(context["role"]) + "\n</head>", 1)
    page = page.replace(
        '<p class="family-view-label" id="familyViewLabel">Fælles overblik</p>',
        f'<p class="family-view-label" id="familyViewLabel">{escape(context["label"])}</p>',
        1,
    )
    page = page.replace(
        '<p class="family-subtitle" id="familySubtitle">Her er et roligt overblik over hjemmet.</p>',
        f'<p class="family-subtitle" id="familySubtitle">{escape(context["subtitle"])}</p>',
        1,
    )
    page = page.replace("<!-- FAMILY_TECHNICAL_STATUS -->", TECHNICAL_STATUS if context["role"] == "owner" else "", 1)
    page = page.replace("<!-- FAMILY_HOME_CARD -->", "" if context["role"] == "child" else HOME_CARD, 1)
    page = page.replace("<!-- FAMILY_TECHNICAL_CARD -->", TECHNICAL_CARD if context["role"] == "owner" else "", 1)
    page = page.replace("<!-- ROUTINE_EDITOR_ACTION -->", ROUTINE_EDITOR_ACTION if context["role"] in {"owner", "adult"} else "", 1)
    page = page.replace("<!-- WALL_DISPLAY_ACTIONS -->", wall_actions, 1)
    page = page.replace("<!-- FAMILY_NAVIGATION -->", navigation_for(context["role"]), 1)
    return page
