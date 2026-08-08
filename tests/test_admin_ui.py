from pathlib import Path

from app import config

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app/static/admin.html").read_text(encoding="utf-8")
ADMIN_SCRIPTS = [
    (ROOT / "app/static/js/admin.js").read_text(encoding="utf-8"),
    (ROOT / "app/static/js/admin-render.js").read_text(encoding="utf-8"),
    (ROOT / "app/static/js/admin-page.js").read_text(encoding="utf-8"),
    (ROOT / "app/static/js/admin-connections.js").read_text(encoding="utf-8"),
    (ROOT / "app/static/js/admin-safety-connections.js").read_text(encoding="utf-8"),
    (ROOT / "app/static/js/admin-screens.js").read_text(encoding="utf-8"),
    (ROOT / "app/static/js/admin-role-visibility.js").read_text(encoding="utf-8"),
    (ROOT / "app/static/js/admin-users.js").read_text(encoding="utf-8"),
]
JAVASCRIPT = "\n".join(ADMIN_SCRIPTS)
CORE_JAVASCRIPT = ADMIN_SCRIPTS[0]
CONNECTION_JAVASCRIPT = ADMIN_SCRIPTS[3] + "\n" + ADMIN_SCRIPTS[4]
SCREEN_JAVASCRIPT = ADMIN_SCRIPTS[5]
ROLE_VISIBILITY_JAVASCRIPT = ADMIN_SCRIPTS[6]
CSS = (ROOT / "app/static/css/admin.css").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


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
        "/api/admin/screens",
        "/api/admin/family-visibility",
        "/api/admin/family-actions",
    ]:
        assert endpoint in JAVASCRIPT
    assert '/static/js/admin-render.js' in CORE_JAVASCRIPT
    assert '/static/js/admin-page.js' in CORE_JAVASCRIPT
    assert '/static/js/admin-safety-connections.js' in CORE_JAVASCRIPT
    assert '/static/js/admin-screens.js' in CORE_JAVASCRIPT
    assert '/static/js/admin-role-visibility.js' in CORE_JAVASCRIPT
    assert '/static/js/admin-users.js' in CORE_JAVASCRIPT
    assert 'options.credentials = "same-origin"' in CORE_JAVASCRIPT
    assert '"X-CSRF-Token": csrfToken' in CORE_JAVASCRIPT
    assert 'window.location.assign("/login?next=/admin")' in CORE_JAVASCRIPT
    assert "requested_by" not in JAVASCRIPT
    assert "source:" not in JAVASCRIPT


def test_admin_screen_management_ui_is_plain_and_safe():
    assert "screenAdminPanel" in SCREEN_JAVASCRIPT
    assert "Skærme" in SCREEN_JAVASCRIPT
    assert "Opret ny skærm" in SCREEN_JAVASCRIPT
    assert "wall-large" in SCREEN_JAVASCRIPT
    assert "wall-tablet" in SCREEN_JAVASCRIPT
    assert "wall-square" in SCREEN_JAVASCRIPT
    assert "Vejr / UV" in SCREEN_JAVASCRIPT
    assert "data-screen-module" in SCREEN_JAVASCRIPT
    assert "data-screen-module-size" in SCREEN_JAVASCRIPT
    assert "module_layout" in SCREEN_JAVASCRIPT
    assert "display_options" in SCREEN_JAVASCRIPT
    assert "screenShowAdminLink" in SCREEN_JAVASCRIPT
    assert "screenShowSafetyStatus" in SCREEN_JAVASCRIPT
    assert "Vis admin-link for ejer" in SCREEN_JAVASCRIPT
    assert "Vis tryghedsstatus" in SCREEN_JAVASCRIPT
    assert "Fuld bredde" in SCREEN_JAVASCRIPT
    assert "deleteScreen" in SCREEN_JAVASCRIPT
    assert 'method: "DELETE"' in SCREEN_JAVASCRIPT
    assert "innerHTML" not in SCREEN_JAVASCRIPT
    assert '["system", "Systemstatus"]' not in SCREEN_JAVASCRIPT
    assert 'system: "Teknisk modul (skjult)"' in SCREEN_JAVASCRIPT
    assert '"Den normale familieoversigt"' in SCREEN_JAVASCRIPT
    assert '"Her vælger du moduler til den normale familieoversigt."' in SCREEN_JAVASCRIPT
    assert '"Her vælger du moduler særskilt for hver væg- eller tabletskærm."' in SCREEN_JAVASCRIPT
    assert "legacyModules" in SCREEN_JAVASCRIPT
    assert "selectedScreen?.module_layout?.[module]" in SCREEN_JAVASCRIPT


def test_admin_role_visibility_ui_is_plain_and_safe():
    assert "roleVisibilityPanel" in ROLE_VISIBILITY_JAVASCRIPT
    assert "Hvem må se hvad?" in ROLE_VISIBILITY_JAVASCRIPT
    assert "Gem synlighed" in ROLE_VISIBILITY_JAVASCRIPT
    assert "Kalender" in ROLE_VISIBILITY_JAVASCRIPT
    assert "Madplan" in ROLE_VISIBILITY_JAVASCRIPT
    assert "Opgaver" in ROLE_VISIBILITY_JAVASCRIPT
    assert "Tryghedsstatus" in ROLE_VISIBILITY_JAVASCRIPT
    assert "Ejer ser altid alt" in ROLE_VISIBILITY_JAVASCRIPT
    assert "data-visibility-role" in ROLE_VISIBILITY_JAVASCRIPT
    assert "data-visibility-feature" in ROLE_VISIBILITY_JAVASCRIPT
    assert "roleActionPanel" in ROLE_VISIBILITY_JAVASCRIPT
    assert "Hvem må ændre hvad?" in ROLE_VISIBILITY_JAVASCRIPT
    assert "Gem rettigheder" in ROLE_VISIBILITY_JAVASCRIPT
    assert "Tilføje opgaver og indkøb" in ROLE_VISIBILITY_JAVASCRIPT
    assert "Afslutte opgaver" in ROLE_VISIBILITY_JAVASCRIPT
    assert "data-action-role" in ROLE_VISIBILITY_JAVASCRIPT
    assert "data-action-feature" in ROLE_VISIBILITY_JAVASCRIPT
    assert 'method: "POST"' in ROLE_VISIBILITY_JAVASCRIPT
    assert "innerHTML" not in ROLE_VISIBILITY_JAVASCRIPT


def test_home_assistant_safety_picker_is_admin_configured():
    for marker in [
        "haInternetStatusEntity",
        "internet_status_entity",
        "createInternetStatusSelect",
        "Vælg fx gatewayens state/status-sensor",
        "haSafetyDoorEntities",
        "haSafetyMotionEntities",
        "haSafetyCameraEntities",
        "safety_door_entities",
        "safety_motion_entities",
        "safety_camera_entities",
    ]:
        assert marker in CONNECTION_JAVASCRIPT
    assert "admin-safety-connections.js" in CORE_JAVASCRIPT


def test_admin_uses_inline_feedback_and_status_aware_actions():
    assert "alert(" not in JAVASCRIPT
    assert "showNotice(" in JAVASCRIPT
    assert 'if (["waiting_approval", "queued"].includes(status)) return ["approve", "deny", "cancel"]' in JAVASCRIPT
    assert 'if (status === "approved") return ["run", "cancel"]' in JAVASCRIPT
    assert "window.confirm(" in JAVASCRIPT
    assert "backgroundRefreshShouldPause" in JAVASCRIPT
    assert "Gem vurderingen for" in CORE_JAVASCRIPT
    assert "Vil du ${action} denne automatiske regel?" in CORE_JAVASCRIPT
    assert "Reglen stopper med at oprette nye automatiske forslag." in CORE_JAVASCRIPT


def test_release_metadata_and_v010_admin_polish():
    assert config.VERSION == "0.22.1"
    assert README.startswith("# Jarvis-os v0.22.1")
    assert "Current release version: `0.22.1`." in README
    assert "## What is new in v0.20.0-alpha.1" in README
    for expected in [
        'label: "Afventer godkendelse"',
        'value: data.overall_status === "ok" ? "Alt kører normalt"',
        "Det er opsætning, ikke en driftsfejl.",
        "Avancerede indstillinger",
        "Kontrollér systemet igen",
        "Starter eller stopper ikke tjenester.",
        "renderAdvancedSummaries",
        "actionGroup.open = waiting > 0",
    ]:
        assert expected in JAVASCRIPT


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
        test_admin_screen_management_ui_is_plain_and_safe,
        test_admin_role_visibility_ui_is_plain_and_safe,
        test_home_assistant_safety_picker_is_admin_configured,
        test_admin_uses_inline_feedback_and_status_aware_actions,
        test_release_metadata_and_v010_admin_polish,
        test_admin_avoids_unsafe_html_and_inline_handlers,
    ]:
        test()
    print("Admin UI tests OK")
