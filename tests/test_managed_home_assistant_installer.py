import os
import tempfile
from pathlib import Path

from app import managed_home_assistant_installer, settings_store


ROOT = Path(__file__).resolve().parents[1]


def test_plan_uses_only_fixed_names_and_is_idempotent():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        initial = managed_home_assistant_installer.managed_install_status(db_path=db_path)
        assert initial["state"] == "not_requested"
        assert initial["installation_started"] is False

        first = managed_home_assistant_installer.request_install_plan({}, db_path=db_path)
        second = managed_home_assistant_installer.request_install_plan({}, db_path=db_path)
        assert first == second
        assert first["state"] == "ready_to_install"
        assert first["installation_started"] is False
        assert first["container_name"] == "jarvis-managed-home-assistant"
        assert first["volume_name"] == "jarvis-managed-home-assistant-config"
        assert first["network_name"] == "jarvis-managed-home-assistant-network"
        assert first["published_port"] == 8123
        assert first["expected_local_url"] == "http://localhost:8123"
        assert settings_store.get_setting(
            managed_home_assistant_installer.STATE_SETTING, db_path=db_path
        ) == "ready_to_install"


def test_browser_options_cannot_override_plan_resources():
    overrides = {
        "container_name": "example-container",
        "image": "example/image:latest",
        "volume_name": "example-volume",
        "network_name": "example-network",
        "published_port": 9999,
        "config_mount_path": "/example",
        "command": "example-command",
    }
    try:
        managed_home_assistant_installer.request_install_plan(overrides)
    except managed_home_assistant_installer.ManagedInstallError as exc:
        assert exc.code == "managed_install_options_not_allowed"
    else:
        raise AssertionError("Browser overrides must be rejected")


def test_foundation_has_no_execution_or_socket_capability():
    source = (ROOT / "app" / "managed_home_assistant_installer.py").read_text(encoding="utf-8")
    production_compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    staging_compose = (ROOT / "compose.staging.yml").read_text(encoding="utf-8")

    for forbidden in ("subprocess", "import docker", "docker.from_env", "docker sdk", "docker.sock", "os.system"):
        assert forbidden not in source.lower()
    assert "/var/run/docker.sock" not in production_compose.split("  jarvis-os:", 1)[1]
    assert "docker.sock" not in staging_compose


def test():
    test_plan_uses_only_fixed_names_and_is_idempotent()
    test_browser_options_cannot_override_plan_resources()
    test_foundation_has_no_execution_or_socket_capability()
    print("Managed Home Assistant installer foundation tests OK")


if __name__ == "__main__":
    test()
