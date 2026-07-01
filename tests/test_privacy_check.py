import shutil
import subprocess
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVACY_SCRIPT = REPOSITORY_ROOT / "scripts" / "privacy_check.sh"


def run(command, cwd, check=True):
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def create_test_repository():
    root = Path(tempfile.mkdtemp())
    (root / "scripts").mkdir()
    shutil.copy2(PRIVACY_SCRIPT, root / "scripts" / "privacy_check.sh")
    run(["git", "init", "-q"], root)
    run(["git", "config", "user.email", "test@example.com"], root)
    run(["git", "config", "user.name", "Example Maintainer"], root)
    (root / "safe.env").write_text("SAFE_MODE=true\n")
    run(["git", "add", "."], root)
    run(["git", "commit", "-qm", "safe baseline"], root)
    return root


def unsafe_fixture_text():
    credential_value = "live-" + "credential-fixture"
    network_value = "10." + "23.45.67"
    key_header = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
    content = "API_" + "TOKEN=" + credential_value + "\n"
    content += "SERVER_" + "IP=" + network_value + "\n"
    content += key_header + "\n"
    return content, credential_value, network_value, key_header


def test_current_checker_detects_fixtures_without_revealing_values():
    root = create_test_repository()
    try:
        content, credential_value, network_value, key_header = unsafe_fixture_text()
        (root / "unsafe.env").write_text(content)
        result = run(["bash", "scripts/privacy_check.sh"], root, check=False)
        assert result.returncode == 1
        lines = set(result.stdout.splitlines())
        assert "unsafe.env:1:credential-assignment" in lines
        assert "unsafe.env:2:private-lan-address" in lines
        assert "unsafe.env:3:private-key" in lines
        assert credential_value not in result.stdout
        assert network_value not in result.stdout
        assert key_header not in result.stdout
        assert all(line.count(":") == 2 for line in lines)
    finally:
        shutil.rmtree(root)


def test_empty_credential_assignments_with_statement_terminators_are_allowed():
    root = create_test_repository()
    try:
        field = "pass" + "word"
        form_field = "form.elements." + field + ".value"
        content = field + ' = ""\n'
        content += field + " = '';\n"
        content += form_field + ' = "";\n'
        content += form_field + " = '';\n"
        (root / "clear.js").write_text(content)
        result = run(["bash", "scripts/privacy_check.sh"], root, check=False)
        assert result.returncode == 0, result.stdout
        assert "credential-assignment" not in result.stdout
    finally:
        shutil.rmtree(root)


def test_dynamic_credential_transport_and_references_are_allowed():
    root = create_test_repository()
    try:
        content = '"X-CSRF-Token": await csrfToken(),\n'
        content += '"Authorization": buildAuthorizationHeader(),\n'
        content += 'headers["X-CSRF-Token"] = getCsrfToken();\n'
        content += 'request.headers["Authorization"] = await buildAuthorizationHeader();\n'
        content += '"Authorization": f"Bearer {self.connection.access_value}",\n'
        content += 'payload = {"password": password_variable}\n'
        content += 'test_client.post("/login", json={"password": supplied_test_password})\n'
        content += 'test_client.post("/login", json={"password": password()})\n'
        content += 'access_value = configured_connection.access_value\n'
        content += 'api_key = process.env.API_KEY;\n'
        content += 'routineCsrfToken = profile.csrf_token || null;\n'
        (root / "dynamic_credentials.txt").write_text(content)
        result = run(["bash", "scripts/privacy_check.sh"], root, check=False)
        assert result.returncode == 0, result.stdout
        assert "credential-assignment" not in result.stdout
    finally:
        shutil.rmtree(root)


def test_hardcoded_credentials_remain_detected_across_formats():
    root = create_test_repository()
    try:
        (root / "unsafe.py").write_text(
            'password = "secret"\n'
            'credentials = {"password": "secret"}\n'
        )
        (root / "unsafe.js").write_text(
            'token = "hardcoded-token";\n'
            '"Authorization": "Bearer hardcoded-secret",\n'
            'headers["X-CSRF-Token"] = "hardcoded-secret";\n'
        )
        (root / "unsafe.json").write_text('"api_key": "hardcoded-key"\n')
        (root / "unsafe.env").write_text("TOKEN=hardcoded-token\n")
        result = run(["bash", "scripts/privacy_check.sh"], root, check=False)
        assert result.returncode == 1
        assert set(result.stdout.splitlines()) == {
            "unsafe.env:1:credential-assignment",
            "unsafe.js:1:credential-assignment",
            "unsafe.js:2:credential-assignment",
            "unsafe.js:3:credential-assignment",
            "unsafe.json:1:credential-assignment",
            "unsafe.py:1:credential-assignment",
            "unsafe.py:2:credential-assignment",
        }
    finally:
        shutil.rmtree(root)


def test_non_empty_javascript_credentials_are_reported_safely():
    root = create_test_repository()
    try:
        field_one = "pass" + "word"
        field_two = "api_" + "token"
        field_three = "client_" + "secret"
        value_one = "fixture-" + "alpha"
        value_two = "fixture-" + "beta"
        content = field_one + ' = "' + value_one + '";\n'
        content += field_two + ' = "' + value_two + '";\n'
        content += field_three + ': "' + value_one + '"\n'
        (root / "credentials.js").write_text(content)
        result = run(["bash", "scripts/privacy_check.sh"], root, check=False)
        assert result.returncode == 1
        lines = result.stdout.splitlines()
        assert set(lines) == {
            "credentials.js:1:credential-assignment",
            "credentials.js:2:credential-assignment",
            "credentials.js:3:credential-assignment",
        }
        assert value_one not in result.stdout
        assert value_two not in result.stdout
        assert all(line.count(":") == 2 for line in lines)
    finally:
        shutil.rmtree(root)


def test_standard_svg_namespace_urls_are_allowed_exactly():
    root = create_test_repository()
    try:
        (root / "namespaces.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" '
            'xml:base="http://www.w3.org/XML/1998/namespace"></svg>\n'
        )
        run(["git", "add", "namespaces.svg"], root)
        result = run(["bash", "scripts/privacy_check.sh"], root, check=False)
        assert result.returncode == 0, result.stdout
        assert "personal-domain" not in result.stdout
    finally:
        shutil.rmtree(root)


def test_other_urls_and_personal_domains_are_still_reported():
    root = create_test_repository()
    try:
        other_w3_url = "http://" + "www.w3.org/2000/not-standard"
        private_url = "https://" + "private-household.invalid/dashboard"
        (root / "urls.txt").write_text(other_w3_url + "\n" + private_url + "\n")
        result = run(["bash", "scripts/privacy_check.sh"], root, check=False)
        assert result.returncode == 1
        assert set(result.stdout.splitlines()) == {
            "urls.txt:1:personal-domain",
            "urls.txt:2:personal-domain",
        }
    finally:
        shutil.rmtree(root)


def test_quoted_response_mapping_keys_are_not_deployment_inventory():
    root = create_test_repository()
    try:
        (root / "response.py").write_text(
            "response = {\n"
            '    "critical_services": critical,\n'
            '    "optional_services": optional,\n'
            "}\n"
        )
        result = run(["bash", "scripts/privacy_check.sh"], root, check=False)
        assert result.returncode == 0, result.stdout
        assert "deployment-inventory" not in result.stdout
    finally:
        shutil.rmtree(root)


def test_bare_deployment_inventory_assignments_are_still_reported_safely():
    root = create_test_repository()
    try:
        (root / "inventory.env").write_text(
            "CRITICAL_SERVICES=service-a,service-b\n"
            'OPTIONAL_SERVICES=["service-a"]\n'
            'ASSET_DEPENDENCIES={"docker:service-a":"docker:service-b"}\n'
        )
        result = run(["bash", "scripts/privacy_check.sh"], root, check=False)
        assert result.returncode == 1
        assert set(result.stdout.splitlines()) == {
            "inventory.env:1:deployment-inventory",
            "inventory.env:2:deployment-inventory",
            "inventory.env:3:service-specific-dependency",
        }
        assert all(line.count(":") == 2 for line in result.stdout.splitlines())
    finally:
        shutil.rmtree(root)


def test_history_mode_finds_removed_private_data_but_current_tree_passes():
    root = create_test_repository()
    try:
        content, credential_value, _, _ = unsafe_fixture_text()
        fixture = root / "temporary.env"
        fixture.write_text(content)
        run(["git", "add", "temporary.env"], root)
        run(["git", "commit", "-qm", "temporary fixture"], root)
        fixture.unlink()
        run(["git", "add", "-u"], root)
        run(["git", "commit", "-qm", "remove fixture"], root)

        current = run(["bash", "scripts/privacy_check.sh"], root, check=False)
        history = run(["bash", "scripts/privacy_check.sh", "--history"], root, check=False)
        assert current.returncode == 0
        assert history.returncode == 1
        assert credential_value not in history.stdout
    finally:
        shutil.rmtree(root)


def test_repository_current_tree_passes_privacy_check():
    result = run(["bash", "scripts/privacy_check.sh"], REPOSITORY_ROOT, check=False)
    assert result.returncode == 0, result.stdout


if __name__ == "__main__":
    for test in [
        test_current_checker_detects_fixtures_without_revealing_values,
        test_empty_credential_assignments_with_statement_terminators_are_allowed,
        test_dynamic_credential_transport_and_references_are_allowed,
        test_hardcoded_credentials_remain_detected_across_formats,
        test_non_empty_javascript_credentials_are_reported_safely,
        test_standard_svg_namespace_urls_are_allowed_exactly,
        test_other_urls_and_personal_domains_are_still_reported,
        test_quoted_response_mapping_keys_are_not_deployment_inventory,
        test_bare_deployment_inventory_assignments_are_still_reported_safely,
        test_history_mode_finds_removed_private_data_but_current_tree_passes,
        test_repository_current_tree_passes_privacy_check,
    ]:
        test()
    print("Privacy check v2 tests OK")
