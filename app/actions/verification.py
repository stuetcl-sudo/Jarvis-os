import time

from app import config
from app.docker_monitor import list_containers


def _verification_result(match: dict | None, observed_state: str | None, expected_state: str, read_error: str | None) -> dict:
    result = dict(match or {})
    result["observed_state"] = observed_state
    result["expected_state"] = expected_state
    if read_error:
        result["verification_error"] = read_error
    return result


def verify_docker_state(asset_id: str, expected_state: str) -> tuple[bool, str, dict]:
    timeout = config.DOCKER_VERIFY_TIMEOUT_SECONDS
    interval = config.DOCKER_VERIFY_INTERVAL_SECONDS
    deadline = time.monotonic() + timeout
    name = asset_id.split(":", 1)[1] if ":" in asset_id else asset_id
    last_match = None
    last_observed_state = None
    last_read_error = None

    while True:
        containers, error = list_containers()
        if error:
            last_read_error = str(error)
        else:
            match = next((item for item in containers if item.get("name") == name), None)
            if match:
                last_match = match
                last_observed_state = match.get("docker_state") or match.get("status")
                if last_observed_state == expected_state:
                    return True, f"Verified {asset_id} is {expected_state}.", _verification_result(match, last_observed_state, expected_state, None)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            result = _verification_result(last_match, last_observed_state, expected_state, last_read_error)
            if last_observed_state is not None:
                reason = f"Verification failed: {asset_id} is {last_observed_state}, expected {expected_state}."
                if last_read_error:
                    reason += f" Last Docker read error: {last_read_error}"
                return False, reason, result
            if last_read_error:
                return False, f"Could not verify Docker state before timeout. Last Docker read error: {last_read_error}", result
            return False, f"Could not verify Docker state before timeout: container {name} was not found.", result

        time.sleep(min(interval, remaining))
