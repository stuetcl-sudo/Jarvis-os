from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {
    name: (ROOT / "app" / "static" / "js" / name).read_text(encoding="utf-8")
    for name in ("login.js", "admin.js", "family.js", "wall.js")
}


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
    admin = SCRIPTS["admin.js"]
    assert "node.textContent = String(text)" in admin
    assert "document.createElement" in admin
    assert "document.createTextNode" in admin
    assert "node.replaceChildren(...children)" in admin
    assert ".addEventListener(" in admin
    assert "escapeHtml" not in admin
    assert "onclick=" not in admin


def test_xss_shaped_payload_can_only_be_assigned_as_text():
    payload = "<" + "img src=x onerror=" + "alert(1)>"
    admin = SCRIPTS["admin.js"]

    assert payload.startswith("<img")
    assert "node.textContent = String(text)" in admin
    assert 'element("p", "", decision.explanation)' in admin
    assert 'element("p", "muted", action.explanation || action.reason)' in admin
    assert 'element("p", "", item.detail)' in admin


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


def test_admin_classification_controls_have_unique_scopes():
    admin = SCRIPTS["admin.js"]
    assert 'function classificationControlId(control, index, scope = "table")' in admin
    assert 'classificationControlId("prot", index)' in admin
    assert 'classificationControlId("auto", index)' in admin
    assert 'classificationSelect(index, container.classification, "unknown")' in admin
    assert 'classificationControlId("prot", index, "unknown")' in admin
    assert 'classificationControlId("auto", index, "unknown")' in admin
    assert 'classifyContainer(index, null, "unknown")' in admin


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
    test_xss_shaped_payload_can_only_be_assigned_as_text()
    test_same_origin_credentials_are_explicit_for_each_frontend()
    test_admin_classification_controls_have_unique_scopes()
    test_existing_frontend_security_contract_remains_present()
    print("Frontend safety tests OK")
