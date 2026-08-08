import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.main_auth import app
from app.version import VERSION


EXPECTED_VERSION = "0.22.1"


def test_release_version_has_one_authoritative_source():
    assert VERSION == EXPECTED_VERSION
    assert config.VERSION == EXPECTED_VERSION


def test_readme_matches_release_version():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert f"# Jarvis-os v{EXPECTED_VERSION}" in readme
    assert f"Current release version: `{EXPECTED_VERSION}`." in readme
    assert "## What is new in v0.22.0" in readme


def test_health_reports_release_version():
    client = TestClient(app)
    try:
        response = client.get("/api/health")
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["version"] == EXPECTED_VERSION


def test_active_compose_and_build_metadata_does_not_contradict_release():
    active_files = [
        Path("Dockerfile"),
        Path("docker-compose.yml"),
        Path("compose.staging.yml"),
        Path("compose.installer.yml"),
        Path("compose.managed-home-assistant.yml"),
        Path("compose.e2e-managed-home-assistant.yml"),
    ]
    for path in active_files:
        source = path.read_text(encoding="utf-8")
        version_labels = re.findall(r"org\.opencontainers\.image\.version\s*[:=]\s*[\"']?([^\s\"']+)", source)
        assert all(value == EXPECTED_VERSION for value in version_labels)


def test_config_does_not_define_a_second_version():
    config_source = Path("app/config.py").read_text(encoding="utf-8")

    assert 'VERSION = "' not in config_source
    assert "from app.version import VERSION" in config_source


def test():
    test_release_version_has_one_authoritative_source()
    test_readme_matches_release_version()
    test_health_reports_release_version()
    test_active_compose_and_build_metadata_does_not_contradict_release()
    test_config_does_not_define_a_second_version()
    print("Release version tests OK")


if __name__ == "__main__":
    test()
