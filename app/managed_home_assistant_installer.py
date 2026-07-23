from dataclasses import asdict, dataclass

from app import settings_store


NOT_REQUESTED = "not_requested"
READY_TO_INSTALL = "ready_to_install"
INSTALLING = "installing"
INSTALLED = "installed"
FAILED = "failed"
INSTALL_STATES = frozenset({
    NOT_REQUESTED,
    READY_TO_INSTALL,
    INSTALLING,
    INSTALLED,
    FAILED,
})

STATE_SETTING = "managed_home_assistant.install_state"
CONTAINER_NAME = "jarvis-managed-home-assistant"
VOLUME_NAME = "jarvis-managed-home-assistant-config"
NETWORK_NAME = "jarvis-managed-home-assistant-network"
IMAGE_NAME = "homeassistant/home-assistant:stable"
EXPECTED_LOCAL_URL = "http://localhost:8123"
CONFIG_MOUNT_PATH = "/config"
PUBLISHED_PORT = 8123

# A future one-shot installer may implement only these fixed operations.
ALLOWED_INSTALL_OPERATIONS = (
    "create_dedicated_network",
    "create_dedicated_volume",
    "create_dedicated_container",
    "start_dedicated_container",
)


class ManagedInstallError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ManagedInstallPlan:
    state: str
    requested: bool
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


def _load_state(db_path=None):
    state = settings_store.get_setting(STATE_SETTING, NOT_REQUESTED, db_path=db_path)
    return state if state in INSTALL_STATES else FAILED


def _plan(state):
    messages = {
        NOT_REQUESTED: "Der er endnu ikke oprettet en installationsplan.",
        READY_TO_INSTALL: "Installationen er ikke startet. Planen afventer ejerens senere bekræftelse.",
        INSTALLING: "Den særskilte installer udfører den bekræftede installation.",
        INSTALLED: "Den administrerede Home Assistant-installation er oprettet.",
        FAILED: "Installationen mislykkedes og er stoppet.",
    }
    return ManagedInstallPlan(
        state=state,
        requested=state != NOT_REQUESTED,
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
        isolation_description="Planen ændrer ikke andre containere, volumes eller netværk.",
        message=messages[state],
    )


def managed_install_status(db_path=None):
    return asdict(_plan(_load_state(db_path=db_path)))


def request_install_plan(options=None, db_path=None):
    if options not in (None, {}):
        raise ManagedInstallError(
            "managed_install_options_not_allowed",
            "Installationsplanen bruger faste, sikre ressourcenavne og kan ikke tilpasses fra browseren.",
        )
    state = _load_state(db_path=db_path)
    if state == NOT_REQUESTED:
        settings_store.set_setting(STATE_SETTING, READY_TO_INSTALL, db_path=db_path)
        state = READY_TO_INSTALL
    return asdict(_plan(state))
