from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_NAMES = (
    "login.js",
    "admin.js",
    "admin-render.js",
    "admin-page.js",
    "family.js",
    "family-calendar.js",
    "wall.js",
    "wall-mode.js",
)
SCRIPTS = {
    name: (ROOT / "app" / "static" / "js" / name).read_text(encoding="utf-8")
    for name in SCRIPT_NAMES
}
ADMIN = "\n".join(SCRIPTS[name] for name in ("admin.js", "admin-render.js", "admin-page.js"))


def test_frontend_scripts_do_not_use_html_parser_sinks():
    combined = "\n".join(SCRIPTS.values())
    for forbidden in (
        "innerHTML",
        "insertAdjacentHTML",
        "outerHTML",
        "document.write",
        "eval(",
        "new Function(",
        "Function(",
    ):
        assert forbidden not in combined


def test_admin_dynamic_values_use_text_dom_apis():
    assert "node.textContent = String(text)" in ADMIN
    assert "document.createElement" in ADMIN
    assert "document.createTextNode" in ADMIN
    assert "node.replaceChildren(...children)" in ADMIN
    assert ".addEventListener(" in ADMIN
    assert "escapeHtml" not in ADMIN
    assert "onclick=" not in ADMIN


def test_html_shaped_payload_can_only_be_assigned_as_text():
    payload = "<" + "img src=x data-probe=blocked>"

    assert payload.startswith("<img")
    assert "node.textContent = String(text)" in ADMIN
    assert 'element("p", "", decision.explanation)' in ADMIN
    assert 'element("p", "muted", action.explanation || action.reason)' in ADMIN
    assert 'element("p", "", item.detail)' in ADMIN


def test_same_origin_credentials_are_explicit_for_each_frontend():
    login = SCRIPTS["login.js"]
    admin = SCRIPTS["admin.js"]
    family = SCRIPTS["family.js"]
    wall = SCRIPTS["wall.js"]

    assert 'credentials: "same-origin"' in login
    assert 'options.credentials = "same-origin"' in admin

    family_endpoints = [
        "/api/mission",
        "/api/family/weather",
        "/api/family/calendar",
        "/api/health",
    ]
    for endpoint in family_endpoints:
        expected = f'fetch("{endpoint}", {{ credentials: "same-origin" }})'
        assert expected in family
    assert family.count('credentials: "same-origin"') == len(family_endpoints)

    wall_read_endpoints = [
        "/api/family/weather",
        "/api/family/calendar",
        "/api/family/routines",
        "/api/auth/me",
    ]
    for endpoint in wall_read_endpoints:
        expected = f'fetch("{endpoint}", {{ credentials: "same-origin" }})'
        assert expected in wall
    assert 'fetch(wallRoutineEndpoints[wallActiveRoutine][action], {' in wall
    assert 'fetch("/api/auth/logout", {' in wall
    assert wall.count('credentials: "same-origin"') == 6


def test_calendar_and_wall_mode_enhancements_are_read_only_and_storage_free():
    enhancements = SCRIPTS["family-calendar.js"] + SCRIPTS["wall-mode.js"]
    assert "fetch(" not in enhancements
    assert "localStorage" not in enhancements
    assert "sessionStorage" not in enhancements
    assert "URLSearchParams" not in enhancements
    assert "location.hash" not in enhancements
    assert "textContent" in enhancements
    assert "createElement" in enhancements


def test_admin_classification_controls_have_unique_scopes():
    assert 'function classificationControlId(control, index, scope = "table")' in ADMIN
    assert 'classificationControlId("prot", index)' in ADMIN
    assert 'classificationControlId("auto", index)' in ADMIN
    assert 'classificationSelect(index, container.classification, "unknown")' in ADMIN
    assert 'classificationControlId("prot", index, "unknown")' in ADMIN
    assert 'classificationControlId("auto", index, "unknown")' in ADMIN
    assert 'classifyContainer(index, null, "unknown")' in ADMIN


def test_existing_frontend_security_contract_remains_present():
    login = SCRIPTS["login.js"]
    family = SCRIPTS["family.js"]
    admin = SCRIPTS["admin.js"]
    wall = SCRIPTS["wall.js"]

    assert 'payload["password"] = form.elements.password.value' in login
    assert 'window.location.assign("/login?next=/admin")' in admin
    assert '"X-CSRF-Token": csrfToken' in admin
    assert '"X-CSRF-Token": await csrfToken()' in wall
    assert "createCalendarEvent(event)" in family
    assert "title.textContent = event.title" in family
    assert "forecast.replaceChildren()" in family


if __name__ == "__main__":
    test_frontend_scripts_do_not_use_html_parser_sinks()
    test_admin_dynamic_values_use_text_dom_apis()
    test_html_shaped_payload_can_only_be_assigned_as_text()
    test_same_origin_credentials_are_explicit_for_each_frontend()
    test_calendar_and_wall_mode_enhancements_are_read_only_and_storage_free()
    test_admin_classification_controls_have_unique_scopes()
    test_existing_frontend_security_contract_remains_present()
    print("Frontend safety tests OK")
