from app.events.types import EventTypes


def default_policies():
    return [
        {
            "policy_id": "policy.unknown_asset_discovered",
            "name": "Unknown asset discovered",
            "description": "Recommend classification when an unknown Docker asset is observed.",
            "enabled": True,
            "priority": 10,
            "trigger_event_type": EventTypes.CONTAINER_UNKNOWN,
            "conditions": {"classification": "unknown"},
            "actions": [{"type": "recommend_classification"}],
            "safety_level": "safe_observation",
        },
        {
            "policy_id": "policy.critical_asset_stopped",
            "name": "Critical asset stopped",
            "description": "Create a critical incident and recommendation when a critical Docker asset stops.",
            "enabled": True,
            "priority": 20,
            "trigger_event_type": EventTypes.CONTAINER_STOPPED,
            "conditions": {"classification": "critical"},
            "actions": [{"type": "create_critical_incident"}, {"type": "recommend_manual_investigation"}],
            "safety_level": "safe_observation",
        },
        {
            "policy_id": "policy.optional_asset_stopped",
            "name": "Optional asset stopped",
            "description": "Recommend and queue a waiting-approval manual restart for optional stopped Docker assets. No automatic restart.",
            "enabled": True,
            "priority": 30,
            "trigger_event_type": EventTypes.CONTAINER_STOPPED,
            "conditions": {"classification": "optional"},
            "actions": [{"type": "recommend_restart"}, {"type": "queue_manual_restart"}],
            "safety_level": "safe_manual_queue",
        },
        {
            "policy_id": "policy.stopped_by_design_asset_stopped",
            "name": "Stopped-by-design asset stopped",
            "description": "Ignore stopped-by-design assets with an explanation.",
            "enabled": True,
            "priority": 40,
            "trigger_event_type": EventTypes.CONTAINER_STOPPED,
            "conditions": {"classification": "stopped_by_design"},
            "actions": [{"type": "ignore"}],
            "safety_level": "safe_observation",
        },
    ]
