from pathlib import Path

from app import config
from app.version import VERSION


EXPECTED_VERSION = "0.20.0-alpha.2"


def test_release_version_has_one_authoritative_source():
    assert VERSION == EXPECTED_VERSION
    assert config.VERSION == EXPECTED_VERSION


def test_readme_matches_release_version():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert f"# Jarvis-os v{EXPECTED_VERSION}" in readme
    assert f"Current development version: `{EXPECTED_VERSION}`." in readme
    assert f"## What is new in v{EXPECTED_VERSION}" in readme


def test_config_does_not_define_a_second_version():
    config_source = Path("app/config.py").read_text(encoding="utf-8")

    assert 'VERSION = "' not in config_source
    assert "from app.version import VERSION" in config_source
