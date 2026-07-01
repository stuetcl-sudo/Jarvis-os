import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()


def replace_once(path, old, new):
    file_path = ROOT / path
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "tests/test_calendar_integration.py",
    "    assert 'fetch(\"/api/family/calendar\")' in javascript\n",
    """    fetch_match = re.search(
        r'fetch\\(\\s*["\\'](/api/family/calendar)["\\']\\s*,\\s*\\{([^{}]*)\\}\\s*\\)',
        javascript,
    )
    assert fetch_match
    options = fetch_match.group(2)
    assert re.search(r'\\bcredentials\\s*:\\s*["\\']same-origin["\\']', options)
    assert not re.search(r'\\bmethod\\s*:', options, re.IGNORECASE)
""",
)

replace_once(
    "tests/test_weather_integration.py",
    "    assert 'fetch(\"/api/family/weather\")' in javascript\n",
    """    fetch_match = re.search(
        r'fetch\\(\\s*["\\'](/api/family/weather)["\\']\\s*,\\s*\\{([^{}]*)\\}\\s*\\)',
        javascript,
    )
    assert fetch_match
    options = fetch_match.group(2)
    assert re.search(r'\\bcredentials\\s*:\\s*["\\']same-origin["\\']', options)
    assert not re.search(r'\\bmethod\\s*:', options, re.IGNORECASE)
""",
)

replace_once(
    "tests/test_dashboard_routes.py",
    """    fetch_calls = re.findall(r'fetch\\(\\s*["\\']([^"\\']+)["\\']\\s*\\)', javascript)
    assert fetch_calls == [
        "/api/mission", "/api/family/weather", "/api/family/calendar", "/api/health",
    ]
""",
    """    fetch_calls = re.findall(
        r'fetch\\(\\s*["\\']([^"\\']+)["\\']\\s*(?:,\\s*\\{([^{}]*)\\})?\\s*\\)',
        javascript,
    )
    assert [endpoint for endpoint, _ in fetch_calls] == [
        "/api/mission", "/api/family/weather", "/api/family/calendar", "/api/health",
    ]
    for _, options in fetch_calls:
        assert re.search(r'\\bcredentials\\s*:\\s*["\\']same-origin["\\']', options)
        assert not re.search(r'\\bmethod\\s*:', options, re.IGNORECASE)
""",
)

replace_once(
    "scripts/privacy_check.sh",
    'SECURITY_HEADER_KEYS = {"authorization", "x_csrf_token"}\n',
    'SECURITY_HEADER_KEYS = {"authorization", "x_csrf_token"}\n'
    'FETCH_CREDENTIAL_MODES = {"omit", "same-origin", "include"}\n',
)

privacy_script = ROOT / "scripts/privacy_check.sh"
text = privacy_script.read_text(encoding="utf-8")
if text.count("HEADER_INDEX_ASSIGNMENT_RE") != 2:
    raise RuntimeError("unexpected indexed assignment matcher count")
text = text.replace("HEADER_INDEX_ASSIGNMENT_RE", "INDEXED_ASSIGNMENT_RE")
if text.count("(Authorization|X-CSRF-Token)") != 1:
    raise RuntimeError("unexpected indexed key pattern count")
text = text.replace(
    "(Authorization|X-CSRF-Token)",
    "([A-Za-z_][A-Za-z0-9_.-]*)",
    1,
)
privacy_script.write_text(text, encoding="utf-8")

replace_once(
    "scripts/privacy_check.sh",
    "def credential_literal(raw_value, value):\n",
    '''def browser_fetch_credential_mode(normalized, raw_value, value, line):
    return (
        normalized == "credentials"
        and value.lower() in FETCH_CREDENTIAL_MODES
        and re.match(r"""^\\s*(?:"credentials"|'credentials'|credentials)\\s*:""", line, re.I)
        and re.fullmatch(r"""(?:"(?:omit|same-origin|include)"|'(?:omit|same-origin|include)')""", raw_value, re.I)
    )


def credential_literal(raw_value, value):
''',
)

replace_once(
    "scripts/privacy_check.sh",
    '''            if credential_key(normalized) and credential_literal(raw_value, value):
                findings.add((number, "credential-assignment"))
''',
    '''            if (
                credential_key(normalized)
                and not browser_fetch_credential_mode(normalized, raw_value, value, line)
                and credential_literal(raw_value, value)
            ):
                findings.add((number, "credential-assignment"))
''',
)

privacy_test = ROOT / "tests/test_privacy_check.py"
text = privacy_test.read_text(encoding="utf-8")
new_safe_test = '''def test_browser_fetch_modes_and_dynamic_form_password_are_allowed():
    root = create_test_repository()
    try:
        scripts = root / "app" / "static" / "js"
        scripts.mkdir(parents=True)
        (scripts / "login.js").write_text(
            'payload["password"] = form.elements.password.value;\\n'
            'const response = await fetch("/api/auth/login", {\\n'
            '  credentials: "same-origin",\\n'
            '});\\n'
        )
        (scripts / "wall.js").write_text(
            'const response = await fetch(endpoint, {\\n'
            '  method: "POST",\\n'
            '  credentials: "same-origin",\\n'
            '});\\n'
            'await fetch("/api/auth/logout", {\\n'
            '  method: "POST",\\n'
            '  credentials: "same-origin",\\n'
            '});\\n'
        )
        result = run(["bash", "scripts/privacy_check.sh"], root, check=False)
        assert result.returncode == 0, result.stdout
        assert "credential-assignment" not in result.stdout
    finally:
        shutil.rmtree(root)


'''
marker = "def test_hardcoded_credentials_remain_detected_across_formats():\n"
if text.count(marker) != 1:
    raise RuntimeError("unexpected hardcoded credential test marker")
text = text.replace(marker, new_safe_test + marker, 1)
text = text.replace(
    '''        javascript_content += 'headers["X-CSRF-Token"] = "' + secret_value + '";\\n'
''',
    '''        javascript_content += 'headers["X-CSRF-Token"] = "' + secret_value + '";\\n'
        javascript_content += 'credentials: "' + secret_value + '",\\n'
        javascript_content += 'payload["' + password_field + '"] = "' + secret_value + '";\\n'
''',
    1,
)
text = text.replace(
    '''            "unsafe.js:3:credential-assignment",
''',
    '''            "unsafe.js:3:credential-assignment",
            "unsafe.js:4:credential-assignment",
            "unsafe.js:5:credential-assignment",
''',
    1,
)
text = text.replace(
    '''        test_dynamic_credential_transport_and_references_are_allowed,
''',
    '''        test_dynamic_credential_transport_and_references_are_allowed,
        test_browser_fetch_modes_and_dynamic_form_password_are_allowed,
''',
    1,
)
privacy_test.write_text(text, encoding="utf-8")

print("Focused v0.9 regression fixes applied.")
