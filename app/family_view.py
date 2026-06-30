from html import escape
from pathlib import Path

FAMILY_TEMPLATE = Path(__file__).resolve().parent / "static" / "index.html"
FAMILY_ROLES = {"owner", "adult", "child", "wall_display"}
PERSONALIZED_ROLES = {"owner", "adult", "child"}

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


def resolve_family_context(current_user):
    if not isinstance(current_user, dict):
        return {"role": "anonymous", "display_name": "", "view": "anonymous", "kiosk": "false"}
    role = current_user.get("role")
    if role not in FAMILY_ROLES:
        return {"role": "anonymous", "display_name": "", "view": "anonymous", "kiosk": "false"}
    display_name = str(current_user.get("display_name") or "").strip() if role in PERSONALIZED_ROLES else ""
    view = "shared-display" if role == "wall_display" else role
    return {"role": role, "display_name": display_name, "view": view, "kiosk": "true" if role == "wall_display" else "false"}


def navigation_for(role):
    if role == "anonymous":
        return '<nav class="family-navigation" aria-label="Bruger"><a class="family-nav-link subtle" href="/login">Log ind</a></nav>'
    links = ['<a class="family-nav-link subtle" href="/login">Skift bruger</a>']
    if role == "owner":
        links.append('<a class="family-nav-link primary" href="/admin">Mission Control</a>')
    return '<nav class="family-navigation" aria-label="Bruger">' + "".join(links) + "</nav>"


def render_family_page(current_user):
    context = resolve_family_context(current_user)
    page = FAMILY_TEMPLATE.read_text(encoding="utf-8")
    body = (
        f'<body data-family-role="{context["role"]}" '
        f'data-family-display-name="{escape(context["display_name"], quote=True)}" '
        f'data-family-view="{context["view"]}" data-family-kiosk="{context["kiosk"]}">'
    )
    page = page.replace(
        '<body data-family-role="anonymous" data-family-display-name="" data-family-view="anonymous" data-family-kiosk="false">',
        body,
        1,
    )
    page = page.replace("<!-- FAMILY_TECHNICAL_STATUS -->", TECHNICAL_STATUS if context["role"] == "owner" else "", 1)
    page = page.replace("<!-- FAMILY_HOME_CARD -->", "" if context["role"] == "child" else HOME_CARD, 1)
    page = page.replace("<!-- FAMILY_TECHNICAL_CARD -->", TECHNICAL_CARD if context["role"] == "owner" else "", 1)
    page = page.replace("<!-- FAMILY_NAVIGATION -->", navigation_for(context["role"]), 1)
    return page
