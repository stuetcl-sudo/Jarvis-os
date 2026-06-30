import shutil
import subprocess
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVACY_SCRIPT = REPOSITORY_ROOT / "scripts" / "privacy_check.sh"


def run(command, cwd, check=True):
    return subprocess.run(command, cwd=cwd, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


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
        test_history_mode_finds_removed_private_data_but_current_tree_passes,
        test_repository_current_tree_passes_privacy_check,
    ]:
        test()
    print("Privacy check v2 tests OK")
