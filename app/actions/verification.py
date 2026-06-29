from app.docker_monitor import list_containers


def verify_docker_state(asset_id: str, expected_state: str) -> tuple[bool, str, dict]:
    containers, error = list_containers()
    if error:
        return False, f"Could not verify Docker state: {error}", {}
    name = asset_id.split(":", 1)[1] if ":" in asset_id else asset_id
    match = next((item for item in containers if item.get("name") == name), None)
    if not match:
        return False, f"Could not verify Docker state: container {name} was not found.", {}
    state = match.get("docker_state") or match.get("status")
    if state == expected_state:
        return True, f"Verified {asset_id} is {expected_state}.", match
    return False, f"Verification failed: {asset_id} is {state}, expected {expected_state}.", match
