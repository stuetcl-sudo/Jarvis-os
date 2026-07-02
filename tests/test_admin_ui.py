from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app/static/admin.html").read_text(encoding="utf-8")
ADMIN_SCRIPTS = [
    (ROOT / "app/static/js/admin.js").read_text(encoding="utf-8"),
    (ROOT / "app/static/js/admin-render.js").read_text(encoding="utf-8"),
    (ROOT / "app/static/js/admin-page.js").read_text(encoding="utf-8"),
]
JAVASCRIPT = "\n".join(ADMIN_SCRIPTS)
CORE_JAVASCRIPT = ADMIN_SCRIPTS[0]
CSS = (ROOT / "app/static/css/admin.css").read_text(encoding="utf-8")


def test_admin_has_plain_language_information_architecture():
    sections = [
        ("overview", "Oversigt"),
        ("home", "Hjemmet"),
        ("modules", "Funktioner"),
        ("connections", "Forbindelser"),
        ("users", "Brugere og adgang"),
        ("system", "Systemstatus"),
        ("advanced", "Avanceret"),
    ]
    for section_id, label in sections:
        assert f'data-admin-target="{section_id}"' in HTML
        assert f'data-admin-section="{section_id}"' in HTML
        assert label in HTML
    assert HTML.index('data-admin-section="overview"') < HTML.index('data-admin-section="advanced"')
    assert "Mission Control + Action Engine" not in HTML
    assert "Event-driven platform" not in HTML


def test_technical_controls_are_grouped_under_advanced():
    advanced = HTML.split('data-admin-section="advanced"', 1)[1]
    for label in [
        "Handlinger og godkendelser",
        "Automatiske regler",
        "Docker og tekniske tjenester",
        "Teknisk inventar",
        "Systemhændelser og historik",
    ]:
        assert label in advanced
    for control_id in [
        "actionQueue",
        "policyList",
        "policyDecisions",
        "unknownContainers",
        "containers",
        "stoppedByDesign",
        "eventFeed",
        "latestAction",
    ]:
        assert f'id="{control_id}"' in advanced


def test_admin_feedback_and_navigation_are_accessible():
    assert 'id="adminNotice"' in HTML
    assert 'aria-live="polite"' in HTML
    assert 'role="tablist"' in HTML
    assert 'role="tabpanel"' in HTML
    assert 'class="skip-link"' in HTML
    assert 'for="assetFilter"' in HTML
    assert "focus-visible" in CSS
    assert "min-height:44px" in CSS.replace(" ", "")
    assert "@media(max-width:860px)" in CSS.replace(" ", "")
    assert "@media(max-width:680px)" in CSS.replace(" ", "")


def test_admin_keeps_existing_api_contract_and_security_helpers():
    for endpoint in [
        "/api/auth/me",
        "/api/auth/logout",
        "/api/worker/run-once",
        "/api/actions/queue",
        "/api/mission",
        "/api/brain",
        "/api/events/latest?limit=20",
        "/api/assets",
        "/api/policies",
        "/api/policy-decisions/latest?limit=20",
        "/api/actions?limit=25",
    ]:
        assert endpoint in JAVASCRIPT
    assert '/static/js/admin-render.js' in CORE_JAVASCRIPT
    assert '/static/js/admin-page.js' in CORE_JAVASCRIPT
    assert 'options.credentials = "same-origin"' in CORE_JAVASCRIPT
    assert '"X-CSRF-Token": csrfToken' in CORE_JAVASCRIPT
    assert 'window.location.assign("/login?next=/admin")' in CORE_JAVASCRIPT
    assert "requested_by" not in JAVASCRIPT
    assert "source:" not in JAVASCRIPT


def test_admin_uses_inline_feedback_and_status_aware_actions():
    assert "alert(" not in JAVASCRIPT
    assert "showNotice(" in JAVASCRIPT
    assert 'if (["waiting_approval", "queued"].includes(status)) return ["approve", "deny", "cancel"]' in JAVASCRIPT
    assert 'if (status === "approved") return ["run", "cancel"]' in JAVASCRIPT
    assert "window.confirm(" in JAVASCRIPT
    assert "backgroundRefreshShouldPause" in JAVASCRIPT


def test_admin_avoids_unsafe_html_and_inline_handlers():
    combined = HTML + "\n" + JAVASCRIPT
    for forbidden in [
        "innerHTML",
        "insertAdjacentHTML",
        "outerHTML",
        "document.write",
        "eval(",
        "new Function(",
        "onclick=",
    ]:
        assert forbidden not in combined


if __name__ == "__main__":
    for test in [
        test_admin_has_plain_language_information_architecture,
        test_technical_controls_are_grouped_under_advanced,
        test_admin_feedback_and_navigation_are_accessible,
        test_admin_keeps_existing_api_contract_and_security_helpers,
        test_admin_uses_inline_feedback_and_status_aware_actions,
        test_admin_avoids_unsafe_html_and_inline_handlers,
    ]:
        test()
    print("Admin UI tests OK")
