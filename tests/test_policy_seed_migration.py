import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from app import config
from app.actions.engine import action_engine
from app.actions.history import initialize_action_tables, list_actions
from app.db import connect, init_db
from app.events.event import Event
from app.events.types import EventTypes
from app.policies.engine import HISTORICAL_POLICY_SEEDS, JARVIS_MANAGED_BY, POLICY_SEED_VERSION, initialize_policy_tables, policy_engine
from app.policies.rules import default_policies


def reset_db():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    config.DB_PATH = tmp.name
    init_db()
    initialize_policy_tables()
    initialize_action_tables()
    return Path(tmp.name)


def insert_policy_from_seed(seed, enabled=1, managed_by=None, seed_version=None, retired=0):
    insert_policy(
        policy_id=seed["policy_id"],
        enabled=enabled,
        managed_by=managed_by,
        seed_version=seed_version,
        retired=retired,
        name=seed["name"],
        description=seed["description"],
        priority=seed["priority"],
        trigger_event_type=seed["trigger_event_type"],
        conditions=seed["conditions"],
        actions=seed["actions"],
        safety_level=seed["safety_level"],
    )


def insert_policy(
    policy_id,
    enabled=1,
    managed_by=None,
    seed_version=None,
    retired=0,
    name="User Policy",
    description="original description",
    priority=999,
    trigger_event_type="Test.Event",
    conditions=None,
    actions=None,
    safety_level="user_safe",
):
    now = "2026-01-01T00:00:00+00:00"
    conn = connect()
    conn.execute(
        """
        INSERT INTO policies (policy_id, name, description, enabled, priority, trigger_event_type, conditions, actions, safety_level, created_at, updated_at, managed_by, seed_version, retired)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            policy_id,
            name,
            description,
            enabled,
            priority,
            trigger_event_type,
            json.dumps(conditions if conditions is not None else {"original": True}, sort_keys=True),
            json.dumps(actions if actions is not None else [{"type": "ignore"}], sort_keys=True),
            safety_level,
            now,
            now,
            managed_by,
            seed_version,
            retired,
        ),
    )
    conn.commit()
    conn.close()


def get_policy(policy_id):
    return policy_engine.get_policy(policy_id)


def historical_seed(policy_id):
    return next(seed for seed in HISTORICAL_POLICY_SEEDS if seed["policy_id"] == policy_id)


def current_seed(policy_id):
    return next(seed for seed in default_policies() if seed["policy_id"] == policy_id)


def logical_policy_view(policy):
    return {
        "policy_id": policy["policy_id"],
        "name": policy["name"],
        "description": policy["description"],
        "enabled": policy["enabled"],
        "priority": policy["priority"],
        "trigger_event_type": policy["trigger_event_type"],
        "conditions": policy["conditions"],
        "actions": policy["actions"],
        "safety_level": policy["safety_level"],
        "managed_by": policy["managed_by"],
        "seed_version": policy["seed_version"],
        "retired": policy["retired"],
    }


def test_fresh_database_receives_current_jarvis_managed_policies():
    path = reset_db()
    try:
        policy_engine.ensure_default_policies()
        policies = {p["policy_id"]: p for p in policy_engine.list_policies()}
        for default in default_policies():
            policy = policies[default["policy_id"]]
            assert policy["managed_by"] == JARVIS_MANAGED_BY
            assert policy["seed_version"] == POLICY_SEED_VERSION
            assert policy["retired"] is False
    finally:
        path.unlink(missing_ok=True)


def test_custom_obsolete_id_is_not_adopted_disabled_or_retired():
    path = reset_db()
    try:
        insert_policy("policy.optional_container_stopped", enabled=1, name="My Custom Old ID", description="not a seed", actions=[{"type": "ignore"}])
        before = logical_policy_view(get_policy("policy.optional_container_stopped"))
        policy_engine.ensure_default_policies()
        after = logical_policy_view(get_policy("policy.optional_container_stopped"))
        assert after == before
    finally:
        path.unlink(missing_ok=True)


def test_custom_current_id_remains_unchanged():
    path = reset_db()
    try:
        insert_policy("policy.optional_asset_stopped", enabled=1, name="My Custom Current ID", description="not a seed", actions=[{"type": "ignore"}])
        before = logical_policy_view(get_policy("policy.optional_asset_stopped"))
        policy_engine.ensure_default_policies()
        after = logical_policy_view(get_policy("policy.optional_asset_stopped"))
        assert after == before
    finally:
        path.unlink(missing_ok=True)


def test_exact_historical_optional_seed_is_adopted_and_retired():
    path = reset_db()
    try:
        seed = historical_seed("policy.optional_container_stopped")
        insert_policy_from_seed(seed, enabled=1, managed_by=None)
        policy_engine.ensure_default_policies()
        old = get_policy("policy.optional_container_stopped")
        assert old is not None
        assert old["enabled"] is False
        assert old["retired"] is True
        assert old["managed_by"] == JARVIS_MANAGED_BY
        assert old["seed_version"] == POLICY_SEED_VERSION
    finally:
        path.unlink(missing_ok=True)


def test_exact_current_seed_with_null_managed_by_is_adopted():
    path = reset_db()
    try:
        seed = current_seed("policy.optional_asset_stopped")
        insert_policy_from_seed(seed, enabled=1, managed_by=None)
        policy_engine.ensure_default_policies()
        policy = get_policy("policy.optional_asset_stopped")
        assert policy["managed_by"] == JARVIS_MANAGED_BY
        assert policy["seed_version"] == POLICY_SEED_VERSION
        assert policy["retired"] is False
        assert any(action.get("type") == "queue_manual_restart" for action in policy["actions"])
    finally:
        path.unlink(missing_ok=True)


def test_manually_disabled_exact_seed_remains_disabled():
    path = reset_db()
    try:
        seed = current_seed("policy.optional_asset_stopped")
        insert_policy_from_seed(seed, enabled=0, managed_by=None)
        policy_engine.ensure_default_policies()
        policy = get_policy("policy.optional_asset_stopped")
        assert policy["enabled"] is False
        assert policy["managed_by"] == JARVIS_MANAGED_BY
        assert policy["retired"] is False
    finally:
        path.unlink(missing_ok=True)


def test_arbitrary_user_created_policy_remains_unchanged():
    path = reset_db()
    try:
        insert_policy("policy.user.custom", enabled=1, managed_by=None, name="My Custom Policy", actions=[{"type": "ignore"}])
        before = logical_policy_view(get_policy("policy.user.custom"))
        policy_engine.ensure_default_policies()
        after = logical_policy_view(get_policy("policy.user.custom"))
        assert after == before
    finally:
        path.unlink(missing_ok=True)


def test_retired_policy_is_not_evaluated():
    path = reset_db()
    try:
        seed = historical_seed("policy.optional_container_stopped")
        insert_policy_from_seed(seed, enabled=1, managed_by=None)
        policy_engine.ensure_default_policies()
        event = Event(source="test", type=EventTypes.CONTAINER_STOPPED, asset_id="docker:example-app", payload={"asset_id": "docker:example-app", "classification": "optional"})
        decisions = policy_engine.evaluate_event(event)
        assert all(d["policy_id"] != "policy.optional_container_stopped" for d in decisions)
    finally:
        path.unlink(missing_ok=True)


def test_migration_is_idempotent_across_repeated_startup():
    path = reset_db()
    try:
        insert_policy_from_seed(historical_seed("policy.critical_container_stopped"), enabled=1, managed_by=None)
        insert_policy_from_seed(current_seed("policy.optional_asset_stopped"), enabled=0, managed_by=None)
        policy_engine.ensure_default_policies()
        first = {p["policy_id"]: logical_policy_view(p) for p in policy_engine.list_policies()}
        policy_engine.ensure_default_policies()
        second = {p["policy_id"]: logical_policy_view(p) for p in policy_engine.list_policies()}
        assert first.keys() == second.keys()
        assert get_policy("policy.critical_container_stopped")["retired"] is True
        assert get_policy("policy.optional_asset_stopped")["enabled"] is False
    finally:
        path.unlink(missing_ok=True)


def test_duplicate_queue_request_does_not_publish_second_action_queued_event():
    path = reset_db()
    try:
        with patch("app.actions.engine.publish") as publish_mock:
            first = action_engine.queue_action(asset_id="docker:example-app", action_type="docker.start_container", requested_by="test", source="test", reason="test")
            second = action_engine.queue_action(asset_id="docker:example-app", action_type="docker.start_container", requested_by="test", source="test", reason="test")
        assert first["action_id"] == second["action_id"]
        assert first["deduplicated"] is False
        assert second["deduplicated"] is True
        assert len(list_actions(10)) == 1
        queued_events = [call for call in publish_mock.call_args_list if call.args[1] == "Action.Queued"]
        assert len(queued_events) == 1
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    for test in [
        test_fresh_database_receives_current_jarvis_managed_policies,
        test_custom_obsolete_id_is_not_adopted_disabled_or_retired,
        test_custom_current_id_remains_unchanged,
        test_exact_historical_optional_seed_is_adopted_and_retired,
        test_exact_current_seed_with_null_managed_by_is_adopted,
        test_manually_disabled_exact_seed_remains_disabled,
        test_arbitrary_user_created_policy_remains_unchanged,
        test_retired_policy_is_not_evaluated,
        test_migration_is_idempotent_across_repeated_startup,
        test_duplicate_queue_request_does_not_publish_second_action_queued_event,
    ]:
        test()
    print("Policy seed migration tests OK")
