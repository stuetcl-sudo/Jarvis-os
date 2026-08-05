"""Fixed-scope, one-shot installer for Jarvis-managed Home Assistant.

The web application may create an opaque request. Only the CLI entry point at the
bottom of this module constructs a Docker client and consumes that request.
"""

import argparse
import hashlib
import os
import secrets
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from app import settings_store


NOT_REQUESTED = "not_requested"
READY_TO_INSTALL = "ready_to_install"
INSTALLING = "installing"
INSTALLED = "installed"
FAILED = "failed"
INSTALL_STATES = frozenset({NOT_REQUESTED, READY_TO_INSTALL, INSTALLING, INSTALLED, FAILED})

STATE_SETTING = "managed_home_assistant.install_state"
ERROR_CODE_SETTING = "managed_home_assistant.error_code"
ERROR_MESSAGE_SETTING = "managed_home_assistant.error_message"
CONTAINER_NAME = "jarvis-managed-home-assistant"
VOLUME_NAME = "jarvis-managed-home-assistant-config"
NETWORK_NAME = "jarvis-managed-home-assistant-network"
IMAGE_NAME = "homeassistant/home-assistant:stable"
EXPECTED_LOCAL_URL = "http://localhost:8123"
CONFIG_MOUNT_PATH = "/config"
PUBLISHED_PORT = 8123
REQUEST_TTL_SECONDS = 600
INSTALLING_STALE_SECONDS = 3600
MANAGED_LABELS = {
    "dk.jarvis.managed": "home-assistant",
    "dk.jarvis.component": "managed-home-assistant-installer",
}

ALLOWED_INSTALL_OPERATIONS = (
    "create_dedicated_network",
    "create_dedicated_volume",
    "create_dedicated_container",
    "start_dedicated_container",
)

REQUEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS managed_home_assistant_requests (
    token_hash TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT
)
"""

SAFE_ERRORS = {
    "request_invalid": "Installationsanmodningen er ugyldig eller allerede brugt.",
    "request_expired": "Installationsanmodningen er udløbet.",
    "resource_conflict": "En fast installationsressource findes med en anden konfiguration.",
    "docker_unavailable": "Docker kunne ikke kontaktes af installationsprogrammet.",
    "installation_failed": "Installationen kunne ikke gennemføres sikkert.",
    "installer_interrupted": "Installationsprogrammet blev afbrudt og skal bekræftes igen.",
}


class ManagedInstallError(ValueError):
    def __init__(self, code, message, status_code=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class ManagedInstallPlan:
    state: str
    requested: bool
    installation_requested: bool
    installation_started: bool
    container_name: str
    image: str
    volume_name: str
    config_mount_path: str
    network_name: str
    published_port: int
    expected_local_url: str
    allowed_operations: tuple[str, ...]
    storage_description: str
    network_description: str
    isolation_description: str
    message: str
    error: dict | None


def _db_path(db_path=None):
    return db_path or os.getenv("DB_PATH", "/data/jarvis.db")


def _connect(db_path=None):
    path = _db_path(db_path)
    settings_store.init_settings_store(path)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(REQUEST_SCHEMA)
    return conn


def _now():
    return datetime.now(timezone.utc)


def _load_state(db_path=None):
    state = settings_store.get_setting(STATE_SETTING, NOT_REQUESTED, db_path=db_path)
    state = state if state in INSTALL_STATES else FAILED
    if state == INSTALLING:
        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT updated_at FROM app_settings WHERE key = ?", (STATE_SETTING,)
            ).fetchone()
        if row and datetime.fromisoformat(row["updated_at"]) <= _now() - timedelta(
            seconds=INSTALLING_STALE_SECONDS
        ):
            _set_failure("installer_interrupted", db_path=db_path)
            return FAILED
    return state


def _has_pending_request(db_path=None, now=None):
    instant = (now or _now()).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM managed_home_assistant_requests "
            "WHERE consumed_at IS NULL AND expires_at > ? LIMIT 1",
            (instant,),
        ).fetchone()
    return bool(row)


def _plan(state, db_path=None):
    messages = {
        NOT_REQUESTED: "Der er endnu ikke oprettet en installationsplan.",
        READY_TO_INSTALL: "Installationsplanen er klar til ejerens bekræftelse.",
        INSTALLING: "Den særskilte installer udfører den bekræftede installation.",
        INSTALLED: "Den administrerede Home Assistant-installation er oprettet.",
        FAILED: "Installationen mislykkedes og er stoppet.",
    }
    error = None
    if state == FAILED:
        code = settings_store.get_setting(ERROR_CODE_SETTING, "installation_failed", db_path=db_path)
        safe_code = code if code in SAFE_ERRORS else "installation_failed"
        error = {
            "code": safe_code,
            "message": SAFE_ERRORS[safe_code],
        }
    return ManagedInstallPlan(
        state=state,
        requested=state != NOT_REQUESTED,
        installation_requested=_has_pending_request(db_path) if state == READY_TO_INSTALL else False,
        installation_started=state in {INSTALLING, INSTALLED},
        container_name=CONTAINER_NAME,
        image=IMAGE_NAME,
        volume_name=VOLUME_NAME,
        config_mount_path=CONFIG_MOUNT_PATH,
        network_name=NETWORK_NAME,
        published_port=PUBLISHED_PORT,
        expected_local_url=EXPECTED_LOCAL_URL,
        allowed_operations=ALLOWED_INSTALL_OPERATIONS,
        storage_description="Home Assistant-data gemmes i den dedikerede Docker-volume.",
        network_description="Home Assistant får sit eget dedikerede Docker-netværk.",
        isolation_description="Installationen ændrer ikke andre containere, volumes eller netværk.",
        message=messages[state],
        error=error,
    )


def managed_install_status(db_path=None):
    return asdict(_plan(_load_state(db_path=db_path), db_path=db_path))


def request_install_plan(options=None, db_path=None):
    if options not in (None, {}):
        raise ManagedInstallError(
            "managed_install_options_not_allowed",
            "Installationsplanen bruger faste, sikre ressourcenavne og kan ikke tilpasses fra browseren.",
        )
    state = _load_state(db_path=db_path)
    if state in {NOT_REQUESTED, FAILED}:
        settings_store.delete_setting(ERROR_CODE_SETTING, db_path=db_path)
        settings_store.delete_setting(ERROR_MESSAGE_SETTING, db_path=db_path)
        settings_store.set_setting(STATE_SETTING, READY_TO_INSTALL, db_path=db_path)
        state = READY_TO_INSTALL
    return asdict(_plan(state, db_path=db_path))


def create_install_request(payload=None, db_path=None, now=None):
    if payload not in (None, {}):
        raise ManagedInstallError(
            "managed_install_options_not_allowed",
            "Installationen bruger kun den faste, godkendte plan.",
        )
    instant = now or _now()
    request_id = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(request_id.encode("ascii")).hexdigest()
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        state = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (STATE_SETTING,)
        ).fetchone()
        if not state or state["value"] != READY_TO_INSTALL:
            raise ManagedInstallError("plan_not_ready", "Installationsplanen er ikke klar.", 409)
        pending = conn.execute(
            "SELECT 1 FROM managed_home_assistant_requests "
            "WHERE consumed_at IS NULL AND expires_at > ? LIMIT 1",
            (instant.isoformat(),),
        ).fetchone()
        if pending:
            raise ManagedInstallError(
                "installation_already_requested", "Installationen er allerede anmodet.", 409
            )
        conn.execute(
            "INSERT INTO managed_home_assistant_requests "
            "(token_hash, created_at, expires_at, consumed_at) VALUES (?, ?, ?, NULL)",
            (token_hash, instant.isoformat(), (instant + timedelta(seconds=REQUEST_TTL_SECONDS)).isoformat()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    result = asdict(_plan(READY_TO_INSTALL, db_path=db_path))
    result["request_expires_at"] = (instant + timedelta(seconds=REQUEST_TTL_SECONDS)).isoformat()
    return result


def _claim_request(db_path=None, now=None):
    instant = now or _now()
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        expired = conn.execute(
            "SELECT 1 FROM managed_home_assistant_requests "
            "WHERE consumed_at IS NULL AND expires_at <= ? LIMIT 1",
            (instant.isoformat(),),
        ).fetchone()
        conn.execute(
            "UPDATE managed_home_assistant_requests SET consumed_at = ? "
            "WHERE consumed_at IS NULL AND expires_at <= ?",
            (instant.isoformat(), instant.isoformat()),
        )
        row = conn.execute(
            "SELECT token_hash FROM managed_home_assistant_requests "
            "WHERE consumed_at IS NULL AND expires_at > ? ORDER BY created_at LIMIT 1",
            (instant.isoformat(),),
        ).fetchone()
        if not row:
            conn.commit()
            code = "request_expired" if expired else "request_invalid"
            raise ManagedInstallError(code, SAFE_ERRORS[code], 409)
        updated = conn.execute(
            "UPDATE managed_home_assistant_requests SET consumed_at = ? "
            "WHERE token_hash = ? AND consumed_at IS NULL",
            (instant.isoformat(), row["token_hash"]),
        ).rowcount
        if updated != 1:
            raise ManagedInstallError("request_invalid", SAFE_ERRORS["request_invalid"], 409)
        conn.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (STATE_SETTING, INSTALLING, instant.isoformat()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _labels_match(resource):
    labels = resource.attrs.get("Labels") or resource.attrs.get("Config", {}).get("Labels") or {}
    return all(labels.get(key) == value for key, value in MANAGED_LABELS.items())


def _get_fixed(collection, name):
    try:
        return collection.get(name)
    except Exception as exc:
        if exc.__class__.__name__ == "NotFound":
            return None
        raise


def _ensure_network(client):
    network = _get_fixed(client.networks, NETWORK_NAME)
    if network:
        if not _labels_match(network) or network.attrs.get("Driver") != "bridge":
            raise ManagedInstallError("resource_conflict", SAFE_ERRORS["resource_conflict"])
        return network
    return client.networks.create(
        NETWORK_NAME, labels=MANAGED_LABELS, driver="bridge", check_duplicate=True
    )


def _ensure_volume(client):
    volume = _get_fixed(client.volumes, VOLUME_NAME)
    if volume:
        if not _labels_match(volume) or volume.attrs.get("Driver") != "local":
            raise ManagedInstallError("resource_conflict", SAFE_ERRORS["resource_conflict"])
        return volume
    return client.volumes.create(VOLUME_NAME, labels=MANAGED_LABELS, driver="local")


def _container_matches(container):
    attrs = container.attrs
    mounts = attrs.get("Mounts") or []
    ports = attrs.get("HostConfig", {}).get("PortBindings", {})
    networks = attrs.get("NetworkSettings", {}).get("Networks", {})
    bindings = ports.get(f"{PUBLISHED_PORT}/tcp") or []
    return (
        _labels_match(container)
        and attrs.get("Config", {}).get("Image") == IMAGE_NAME
        and len(mounts) == 1
        and any(
            mount.get("Type") == "volume"
            and mount.get("Name") == VOLUME_NAME
            and mount.get("Destination") == CONFIG_MOUNT_PATH
            and mount.get("RW") is True
            for mount in mounts
        )
        and set(ports) == {f"{PUBLISHED_PORT}/tcp"}
        and len(bindings) == 1
        and all(
            binding.get("HostPort") == str(PUBLISHED_PORT)
            and binding.get("HostIp", "") in {"", "0.0.0.0"}
            for binding in bindings
        )
        and attrs.get("HostConfig", {}).get("RestartPolicy", {}).get("Name")
        == "unless-stopped"
        and set(networks) == {NETWORK_NAME}
    )


def _ensure_container(client):
    container = _get_fixed(client.containers, CONTAINER_NAME)
    if container:
        if not _container_matches(container):
            raise ManagedInstallError("resource_conflict", SAFE_ERRORS["resource_conflict"])
    else:
        create_options = {
            "name": CONTAINER_NAME,
            "detach": True,
            "labels": MANAGED_LABELS,
            "network": NETWORK_NAME,
            "ports": {f"{PUBLISHED_PORT}/tcp": PUBLISHED_PORT},
            "restart_policy": {"Name": "unless-stopped"},
            "volumes": {VOLUME_NAME: {"bind": CONFIG_MOUNT_PATH, "mode": "rw"}},
        }
        try:
            container = client.containers.create(IMAGE_NAME, **create_options)
        except Exception as exc:
            if exc.__class__.__name__ != "ImageNotFound":
                raise
            client.images.pull(IMAGE_NAME)
            container = client.containers.create(IMAGE_NAME, **create_options)
    container.reload()
    if not _container_matches(container):
        raise ManagedInstallError("resource_conflict", SAFE_ERRORS["resource_conflict"])
    if container.status != "running":
        container.start()
        container.reload()
    if container.status != "running":
        raise ManagedInstallError("installation_failed", SAFE_ERRORS["installation_failed"])
    return container


def _preflight(client):
    network = _get_fixed(client.networks, NETWORK_NAME)
    volume = _get_fixed(client.volumes, VOLUME_NAME)
    container = _get_fixed(client.containers, CONTAINER_NAME)
    if network and (not _labels_match(network) or network.attrs.get("Driver") != "bridge"):
        raise ManagedInstallError("resource_conflict", SAFE_ERRORS["resource_conflict"])
    if volume and (not _labels_match(volume) or volume.attrs.get("Driver") != "local"):
        raise ManagedInstallError("resource_conflict", SAFE_ERRORS["resource_conflict"])
    if container and not _container_matches(container):
        raise ManagedInstallError("resource_conflict", SAFE_ERRORS["resource_conflict"])


def _set_failure(code, db_path=None):
    safe_code = code if code in SAFE_ERRORS else "installation_failed"
    instant = _now().isoformat()
    with _connect(db_path) as conn:
        for key, value in (
            (STATE_SETTING, FAILED),
            (ERROR_CODE_SETTING, safe_code),
            (ERROR_MESSAGE_SETTING, SAFE_ERRORS[safe_code]),
        ):
            conn.execute(
                "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key, value, instant),
            )


def run_installation(docker_client=None, db_path=None, now=None, docker_client_factory=None):
    try:
        _claim_request(db_path=db_path, now=now)
        if docker_client is None:
            try:
                docker_client = docker_client_factory()
            except Exception as exc:
                raise ManagedInstallError(
                    "docker_unavailable", SAFE_ERRORS["docker_unavailable"]
                ) from exc
        _preflight(docker_client)
        _ensure_network(docker_client)
        _ensure_volume(docker_client)
        _ensure_container(docker_client)
        _preflight(docker_client)
        settings_store.delete_setting(ERROR_CODE_SETTING, db_path=db_path)
        settings_store.delete_setting(ERROR_MESSAGE_SETTING, db_path=db_path)
        settings_store.set_setting(STATE_SETTING, INSTALLED, db_path=db_path)
        return managed_install_status(db_path=db_path)
    except ManagedInstallError as exc:
        if exc.code not in {"request_invalid", "request_expired"}:
            _set_failure(exc.code, db_path=db_path)
        raise
    except Exception as exc:
        _set_failure("installation_failed", db_path=db_path)
        raise ManagedInstallError("installation_failed", SAFE_ERRORS["installation_failed"]) from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kør den faste Jarvis Home Assistant-installation én gang.")
    parser.parse_args(argv)
    import docker

    try:
        result = run_installation(docker_client_factory=docker.from_env, db_path=_db_path())
    except ManagedInstallError as exc:
        print(f"{exc.code}: {exc.message}")
        return 1
    except Exception:
        print(f"docker_unavailable: {SAFE_ERRORS['docker_unavailable']}")
        return 1
    print(result["message"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
