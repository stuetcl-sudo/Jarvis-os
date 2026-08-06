import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app import managed_home_assistant_installer as installer
from app import settings_store


ROOT = Path(__file__).resolve().parents[1]


class NotFound(Exception):
    pass


class Resource:
    def __init__(self, attrs, status=None, calls=None):
        self.attrs = attrs
        self.status = status
        self.calls = calls if calls is not None else []

    def reload(self):
        self.calls.append(("reload",))

    def start(self):
        self.calls.append(("start",))
        self.status = "running"


class Collection:
    def __init__(self, kind, resources, calls):
        self.kind = kind
        self.resources = resources
        self.calls = calls

    def get(self, name):
        self.calls.append((f"{self.kind}.get", name))
        if name not in self.resources:
            raise NotFound(name)
        return self.resources[name]

    def create(self, *args, **kwargs):
        self.calls.append((f"{self.kind}.create", args, kwargs))
        name = kwargs.get("name") or args[0]
        if self.kind == "networks":
            resource = Resource({"Labels": kwargs["labels"], "Driver": kwargs["driver"]})
        elif self.kind == "volumes":
            resource = Resource({"Labels": kwargs["labels"], "Driver": kwargs["driver"]})
        else:
            resource = expected_container("created", calls=self.calls)
        self.resources[name] = resource
        return resource


class FakeDockerClient:
    def __init__(self, networks=None, volumes=None, containers=None):
        self.calls = []
        self.networks = Collection("networks", networks or {}, self.calls)
        self.volumes = Collection("volumes", volumes or {}, self.calls)
        self.containers = Collection("containers", containers or {}, self.calls)


class Images:
    def __init__(self, calls):
        self.calls = calls

    def pull(self, image):
        self.calls.append(("images.pull", image))


class MissingImageContainers(Collection):
    def __init__(self, resources, calls):
        super().__init__("containers", resources, calls)
        self.missing = True

    def create(self, *args, **kwargs):
        if self.missing:
            self.missing = False
            self.calls.append(("containers.create", args, kwargs))
            error_type = type("ImageNotFound", (Exception,), {})
            raise error_type("raw private registry diagnostic")
        return super().create(*args, **kwargs)


def managed_resource(driver):
    return Resource({"Labels": dict(installer.MANAGED_LABELS), "Driver": driver})


def expected_container(status="running", calls=None, labels=None):
    return Resource(
        {
            "Config": {"Image": installer.IMAGE_NAME, "Labels": dict(labels or installer.MANAGED_LABELS)},
            "Mounts": [{
                "Type": "volume",
                "Name": installer.VOLUME_NAME,
                "Destination": installer.CONFIG_MOUNT_PATH,
                "RW": True,
            }],
            "HostConfig": {
                "PortBindings": {"8123/tcp": [{"HostIp": "", "HostPort": "8123"}]},
                "RestartPolicy": {"Name": "unless-stopped"},
            },
            "NetworkSettings": {"Networks": {installer.NETWORK_NAME: {}}},
        },
        status=status,
        calls=calls,
    )


def planned_request(db_path, now=None):
    installer.request_install_plan({}, db_path=db_path)
    return installer.create_install_request({}, db_path=db_path, now=now)


def test_plan_uses_only_fixed_names_and_is_idempotent():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        initial = installer.managed_install_status(db_path=db_path)
        assert initial["state"] == "not_requested"
        first = installer.request_install_plan({}, db_path=db_path)
        second = installer.request_install_plan({}, db_path=db_path)
        assert first == second
        assert first["state"] == "ready_to_install"
        assert first["container_name"] == installer.CONTAINER_NAME
        assert first["volume_name"] == installer.VOLUME_NAME
        assert first["network_name"] == installer.NETWORK_NAME
        assert first["published_port"] == 8123
        assert "expected_local_url" not in first
        assert installer.BACKEND_URL == "http://jarvis-managed-home-assistant:8123"


def test_request_requires_plan_rejects_duplicate_replay_and_expiry():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        try:
            installer.create_install_request({}, db_path=db_path)
        except installer.ManagedInstallError as exc:
            assert exc.code == "plan_not_ready"
        else:
            raise AssertionError("A request without a plan must fail")

        instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
        response = planned_request(db_path, instant)
        assert "request_token" not in response
        try:
            installer.create_install_request({}, db_path=db_path, now=instant)
        except installer.ManagedInstallError as exc:
            assert exc.code == "installation_already_requested"
        else:
            raise AssertionError("A concurrent pending request must fail")

        client = FakeDockerClient()
        installer.run_installation(client, db_path=db_path, now=instant)
        try:
            installer.run_installation(client, db_path=db_path, now=instant)
        except installer.ManagedInstallError as exc:
            assert exc.code == "request_invalid"
        else:
            raise AssertionError("A consumed request must not replay")

        expired_db = os.path.join(folder, "expired.db")
        planned_request(expired_db, instant)
        try:
            installer.run_installation(
                FakeDockerClient(), db_path=expired_db,
                now=instant + timedelta(seconds=installer.REQUEST_TTL_SECONDS + 1),
            )
        except installer.ManagedInstallError as exc:
            assert exc.code == "request_expired"
        else:
            raise AssertionError("An expired request must fail")


def test_installer_uses_fixed_resources_and_transitions_to_installed():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        client = FakeDockerClient()
        planned_request(db_path)
        observed_states = []
        original_preflight = installer._preflight

        def observe_preflight(docker_client):
            observed_states.append(settings_store.get_setting(installer.STATE_SETTING, db_path=db_path))
            return original_preflight(docker_client)

        with patch.object(installer, "_preflight", side_effect=observe_preflight):
            result = installer.run_installation(client, db_path=db_path)
        assert result["state"] == "installed"
        assert observed_states == [installer.INSTALLING, installer.INSTALLING]
        assert client.calls[:3] == [
            ("networks.get", installer.NETWORK_NAME),
            ("volumes.get", installer.VOLUME_NAME),
            ("containers.get", installer.CONTAINER_NAME),
        ]
        creates = [call for call in client.calls if call[0].endswith(".create")]
        assert [call[0] for call in creates] == ["networks.create", "volumes.create", "containers.create"]
        container_args = creates[2]
        assert container_args[1] == (installer.IMAGE_NAME,)
        assert container_args[2]["name"] == installer.CONTAINER_NAME
        assert container_args[2]["network"] == installer.NETWORK_NAME
        assert container_args[2]["ports"] == {"8123/tcp": 8123}
        assert container_args[2]["volumes"] == {
            installer.VOLUME_NAME: {"bind": "/config", "mode": "rw"}
        }


def test_conflict_is_refused_before_changes_and_safe_failure_is_stored():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        unrelated = Resource({"Labels": {"owner": "someone-else"}})
        client = FakeDockerClient(volumes={installer.VOLUME_NAME: unrelated})
        try:
            planned_request(db_path)
            installer.run_installation(client, db_path=db_path)
        except installer.ManagedInstallError as exc:
            assert exc.code == "resource_conflict"
        else:
            raise AssertionError("A conflicting fixed resource must fail")
        assert not any(call[0].endswith(".create") for call in client.calls)
        status = installer.managed_install_status(db_path=db_path)
        assert status["state"] == "failed"
        assert status["error"] == {
            "code": "resource_conflict",
            "message": installer.SAFE_ERRORS["resource_conflict"],
        }


def test_resources_with_additional_labels_are_refused():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        labels = {**installer.MANAGED_LABELS, "unexpected.label": "not-managed"}
        network = Resource({"Labels": labels, "Driver": "bridge"})
        client = FakeDockerClient(networks={installer.NETWORK_NAME: network})
        planned_request(db_path)

        try:
            installer.run_installation(client, db_path=db_path)
        except installer.ManagedInstallError as exc:
            assert exc.code == "resource_conflict"
        else:
            raise AssertionError("A resource with non-exact labels must fail")

        assert not any(call[0].endswith(".create") for call in client.calls)


def test_container_requires_managed_labels_and_allows_image_labels():
    exact = expected_container()
    inherited = expected_container(labels={
        **installer.MANAGED_LABELS,
        "io.hass.type": "core",
        "io.hass.version": "2026.8.0",
        "org.opencontainers.image.title": "Home Assistant",
    })
    missing = dict(installer.MANAGED_LABELS)
    missing.pop("dk.jarvis.component")
    incorrect = {
        **installer.MANAGED_LABELS,
        "dk.jarvis.managed": "something-else",
        "io.hass.type": "core",
    }
    unrelated = {
        "io.hass.type": "core",
        "org.opencontainers.image.title": "Home Assistant",
    }

    assert installer._container_matches(exact)
    assert installer._container_matches(inherited)
    assert not installer._container_matches(expected_container(labels=missing))
    assert not installer._container_matches(expected_container(labels=incorrect))
    assert not installer._container_matches(expected_container(labels=unrelated))


def test_network_and_volume_labels_remain_exact():
    exact_network = managed_resource("bridge")
    exact_volume = managed_resource("local")
    additional_network = Resource({
        "Labels": {**installer.MANAGED_LABELS, "io.hass.type": "core"},
        "Driver": "bridge",
    })
    additional_volume = Resource({
        "Labels": {**installer.MANAGED_LABELS, "io.hass.type": "core"},
        "Driver": "local",
    })

    assert installer._labels_match_exactly(exact_network)
    assert installer._labels_match_exactly(exact_volume)
    assert not installer._labels_match_exactly(additional_network)
    assert not installer._labels_match_exactly(additional_volume)


def test_missing_image_pulls_only_the_fixed_image():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        client = FakeDockerClient()
        client.images = Images(client.calls)
        client.containers = MissingImageContainers({}, client.calls)
        planned_request(db_path)
        assert installer.run_installation(client, db_path=db_path)["state"] == "installed"
        assert [call for call in client.calls if call[0] == "images.pull"] == [
            ("images.pull", installer.IMAGE_NAME)
        ]


def test_docker_connection_failure_is_stored_without_raw_exception():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        planned_request(db_path)

        def unavailable():
            raise RuntimeError("raw private Docker diagnostic")

        try:
            installer.run_installation(docker_client_factory=unavailable, db_path=db_path)
        except installer.ManagedInstallError as exc:
            assert exc.code == "docker_unavailable"
            assert "raw private" not in exc.message
        else:
            raise AssertionError("An unavailable Docker client must fail")
        status = installer.managed_install_status(db_path=db_path)
        assert status["state"] == "failed"
        assert status["error"] == {
            "code": "docker_unavailable",
            "message": installer.SAFE_ERRORS["docker_unavailable"],
        }


def test_existing_expected_resources_are_idempotent_and_unrelated_are_untouched():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        unrelated_network = managed_resource("bridge")
        unrelated_volume = managed_resource("local")
        unrelated_container = expected_container()
        client = FakeDockerClient(
            networks={installer.NETWORK_NAME: managed_resource("bridge"), "other-network": unrelated_network},
            volumes={installer.VOLUME_NAME: managed_resource("local"), "other-volume": unrelated_volume},
            containers={installer.CONTAINER_NAME: expected_container(calls=[]), "other-container": unrelated_container},
        )
        planned_request(db_path)
        installer.run_installation(client, db_path=db_path)
        assert not any(call[0].endswith(".create") for call in client.calls)
        assert all("other-" not in str(call) for call in client.calls)
        assert unrelated_container.calls == []


def test_no_shell_and_compose_boundaries():
    source = (ROOT / "app" / "managed_home_assistant_installer.py").read_text(encoding="utf-8").lower()
    production = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    staging = (ROOT / "compose.staging.yml").read_text(encoding="utf-8")
    one_shot = (ROOT / "compose.installer.yml").read_text(encoding="utf-8")
    overlay = (ROOT / "compose.managed-home-assistant.yml").read_text(encoding="utf-8")
    for forbidden in ("subprocess", "os.system", "shell=true", "create_container("):
        assert forbidden not in source
    assert "/var/run/docker.sock" not in production.split("  jarvis-os:", 1)[1]
    assert "docker.sock" not in staging
    assert "/var/run/docker.sock" in one_shot
    assert "profiles:" in one_shot
    assert "ports:" not in one_shot
    assert "env_file:" not in one_shot
    assert "privileged:" not in one_shot
    assert "network_mode:" not in one_shot
    assert "MANAGED_HA_INSTALL_REQUEST" not in one_shot
    assert one_shot.count("/var/run/docker.sock") == 2
    assert "docker.sock" not in overlay
    assert "network_mode:" not in overlay
    assert "external: true" in overlay
    assert f"name: {installer.NETWORK_NAME}" in overlay
    assert "- default" in overlay
    assert "- managed_home_assistant_network" in overlay
    assert installer.NETWORK_NAME not in staging
    assert "fake" in FakeDockerClient.__name__.lower()


def test_concurrent_confirmations_and_workers_have_one_winner():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        installer.request_install_plan({}, db_path=db_path)
        barrier = threading.Barrier(2)
        confirmations = []

        def confirm():
            barrier.wait()
            try:
                installer.create_install_request({}, db_path=db_path)
                confirmations.append("created")
            except installer.ManagedInstallError as exc:
                confirmations.append(exc.code)

        threads = [threading.Thread(target=confirm) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sorted(confirmations) == ["created", "installation_already_requested"]

        barrier = threading.Barrier(2)
        workers = []

        def work():
            barrier.wait()
            try:
                installer.run_installation(FakeDockerClient(), db_path=db_path)
                workers.append("installed")
            except installer.ManagedInstallError as exc:
                workers.append(exc.code)

        threads = [threading.Thread(target=work) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sorted(workers) == ["installed", "request_invalid"]


def test_stale_installing_state_fails_safely_and_can_be_replanned():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        planned_request(db_path)
        installer._claim_request(db_path=db_path)
        stale_time = datetime.now(timezone.utc) - timedelta(
            seconds=installer.INSTALLING_STALE_SECONDS + 1
        )
        with installer._connect(db_path) as conn:
            conn.execute(
                "UPDATE app_settings SET updated_at = ? WHERE key = ?",
                (stale_time.isoformat(), installer.STATE_SETTING),
            )
        status = installer.managed_install_status(db_path=db_path)
        assert status["state"] == "failed"
        assert status["error"] == {
            "code": "installer_interrupted",
            "message": installer.SAFE_ERRORS["installer_interrupted"],
        }
        assert installer.request_install_plan({}, db_path=db_path)["state"] == "ready_to_install"


def test():
    test_plan_uses_only_fixed_names_and_is_idempotent()
    test_request_requires_plan_rejects_duplicate_replay_and_expiry()
    test_installer_uses_fixed_resources_and_transitions_to_installed()
    test_conflict_is_refused_before_changes_and_safe_failure_is_stored()
    test_resources_with_additional_labels_are_refused()
    test_container_requires_managed_labels_and_allows_image_labels()
    test_network_and_volume_labels_remain_exact()
    test_missing_image_pulls_only_the_fixed_image()
    test_docker_connection_failure_is_stored_without_raw_exception()
    test_existing_expected_resources_are_idempotent_and_unrelated_are_untouched()
    test_no_shell_and_compose_boundaries()
    test_concurrent_confirmations_and_workers_have_one_winner()
    test_stale_installing_state_fails_safely_and_can_be_replanned()
    print("Managed Home Assistant installer tests OK")


if __name__ == "__main__":
    test()
