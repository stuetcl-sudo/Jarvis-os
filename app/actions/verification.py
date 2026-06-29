import time

from app.docker_monitor import list_containers


def read_docker_asset_state(asset_id: str) -> tuple[str | None, dict]:
    containers, error = list_containers()
    if error:
        return None, {"error": error}
    name = asset_id.split(":", 1)[1] if ":" in asset_id else asset_id
    match = next((item for item in containers if item.get("name") == name), None)
    if not match:
        return None, {"error": f"container {name} was not found"}
    return match.get("docker_state") or match.get("status"), match


def verify_docker_state(asset_id: str, expected_state: str, timeout_seconds: float = 12.0, interval_seconds: float = 0.75) -> tuple[bool, str, dict]:
    deadline = time.monotonic() + timeout_seconds
    final_live = {}
    final_state = None
    polls = 0
    while time.monotonic() <= deadline:
        polls += 1
        final_state, final_live = read_docker_asset_state(asset_id)
        final_live = {**(final_live or {}), "polls": polls, "final_state": final_state}
        if final_state == expected_state:
            return True, f"Verified {asset_id} is {expected_state} after {polls} poll(s).", final_live
        time.sleep(interval_seconds)
    return False, f"Verification timeout: {asset_id} final state was {final_state}, expected {expected_state}.", final_live
