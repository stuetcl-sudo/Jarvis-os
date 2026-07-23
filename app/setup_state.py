from app import config, home_setup
from app.auth.service import auth_service
from app.home_assistant import HomeAssistantConfigurationError, load_home_assistant_connection


BOOTSTRAP_REQUIRED = "bootstrap_required"
OWNER_CREATED = "owner_created"
HOME_ASSISTANT_REQUIRED = "home_assistant_required"
READY = "ready"
SETUP_STATES = frozenset({
    BOOTSTRAP_REQUIRED,
    OWNER_CREATED,
    HOME_ASSISTANT_REQUIRED,
    READY,
})


def _home_assistant_valid():
    try:
        return load_home_assistant_connection() is not None
    except (HomeAssistantConfigurationError, OSError, RuntimeError):
        return False


def setup_status(db_path=None):
    """Return the single authoritative first-run state for this installation."""
    if auth_service.bootstrap_required():
        state = BOOTSTRAP_REQUIRED
        basic_setup_complete = False
        home_assistant_valid = False
    else:
        basic_setup_complete = home_setup.load_home_settings(
            db_path=db_path or config.DB_PATH
        )["completed"]
        home_assistant_valid = _home_assistant_valid()
        if not basic_setup_complete:
            state = OWNER_CREATED
        elif not home_assistant_valid:
            state = HOME_ASSISTANT_REQUIRED
        else:
            state = READY

    return {
        "state": state,
        "owner_created": state != BOOTSTRAP_REQUIRED,
        "basic_setup_complete": basic_setup_complete,
        "home_assistant_valid": home_assistant_valid,
        "ready": state == READY,
    }
