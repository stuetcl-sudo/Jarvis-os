import json
from pathlib import Path


def validate_live_snapshots():
    containers_response = json.loads(Path("/tmp/jarvis-containers.json").read_text())
    containers = containers_response["containers"]
    mission = json.loads(Path("/tmp/jarvis-mission.json").read_text())
    assets = json.loads(Path("/tmp/jarvis-assets.json").read_text())["assets"]
    policies = json.loads(Path("/tmp/jarvis-policies.json").read_text())["policies"]
    decisions = json.loads(Path("/tmp/jarvis-policy-decisions.json").read_text())["decisions"]
    actions = json.loads(Path("/tmp/jarvis-actions.json").read_text())["actions"]
    asset_ids = {asset["asset_id"] for asset in assets}
    mission_containers = mission.get("containers", [])
    mission_by_name = {container["name"]: container for container in mission_containers}

    if not policies:
        raise SystemExit("Policy Engine has no policies")
    for policy in policies:
        for field in ["policy_id", "name", "enabled", "priority", "trigger_event_type", "conditions", "actions", "safety_level", "managed_by", "seed_version", "retired"]:
            if field not in policy:
                raise SystemExit(f"Missing {field} on policy")
    for decision in decisions:
        for field in ["decision_id", "policy_id", "timestamp", "matched", "allowed", "action", "reason", "explanation", "dry_run"]:
            if field not in decision:
                raise SystemExit(f"Missing {field} on policy decision")
    forbidden_action_types = {
        "docker." + "stop_container",
        "docker." + "delete_container",
        "docker." + "prune",
        "docker." + "exec",
        "file." + "delete",
        "firewall." + "change",
        "dns." + "change",
        "volume." + "delete",
    }
    for action in actions:
        for field in ["action_id", "created_at", "updated_at", "requested_by", "source", "asset_id", "action_type", "status", "requires_approval", "approved", "safety_status", "reason", "explanation", "payload", "result"]:
            if field not in action:
                raise SystemExit(f"Missing {field} on action")
        if action["action_type"] in forbidden_action_types:
            raise SystemExit(f"Disallowed action type present: {action['action_type']}")

    if "docker_read_at" not in containers_response:
        raise SystemExit("Missing docker_read_at in /api/containers")
    if "docker_read_at" not in mission.get("docker", {}):
        raise SystemExit("Missing docker_read_at in /api/mission docker object")
    if len(containers) != mission["docker"]["total"] or len(containers) != len(mission_containers):
        raise SystemExit("Docker totals disagree")
    for container in containers:
        name = container.get("name")
        expected_asset = f"docker:{name}"
        if container.get("asset_id") != expected_asset:
            raise SystemExit(f"Missing or wrong asset_id for {name}")
        if expected_asset not in asset_ids:
            raise SystemExit(f"Asset Registry missing {expected_asset}")
        if name not in mission_by_name:
            raise SystemExit(f"{name} missing from /api/mission containers list")
        mission_container = mission_by_name[name]
        for item, label in [(container, "/api/containers"), (mission_container, "/api/mission")]:
            if item.get("status") != item.get("docker_state"):
                raise SystemExit(f"{label} status/docker_state mismatch for {name}")
            for field in ["docker_state", "docker_status", "status", "health_status", "read_at", "asset_id"]:
                if field not in item:
                    raise SystemExit(f"Missing {field} on {name} in {label}")
        if container.get("docker_state") != mission_container.get("docker_state") or container.get("status") != mission_container.get("status"):
            raise SystemExit(f"Docker state mismatch for {name}")

    class_total = sum(len(mission.get(key, [])) for key in ["critical_services", "optional_services", "stopped_by_design", "unknown_containers"])
    if class_total != len(containers):
        raise SystemExit("Classified sections do not include all containers")
    if sum(1 for container in containers if container.get("docker_state") == "running") != mission["docker"]["running"]:
        raise SystemExit("Docker running count disagrees")
    if sum(1 for container in containers if container.get("docker_state") == "exited") != mission["docker"]["stopped"]:
        raise SystemExit("Docker stopped count disagrees")


if __name__ == "__main__":
    validate_live_snapshots()
    print("Live Docker + Asset Registry + Event Engine + Policy Engine + Action Engine regression OK")
