import json
from typing import Any

from app.assets.registry import asset_registry
from app.db import connect
from app.events.event import Event
from app.policies.actions import create_critical_incident, create_recommendation, deny, ignore
from app.policies.explain import explain_match
from app.policies.policy import Decision, now_iso
from app.policies.rules import default_policies

POLICY_SCHEMA = """
CREATE TABLE IF NOT EXISTS policies (
    policy_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 100,
    trigger_event_type TEXT NOT NULL,
    conditions TEXT NOT NULL,
    actions TEXT NOT NULL,
    safety_level TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

DECISION_SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_decisions (
    decision_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    asset_id TEXT,
    event_id TEXT,
    matched INTEGER NOT NULL,
    allowed INTEGER NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    explanation TEXT NOT NULL,
    dry_run INTEGER NOT NULL DEFAULT 1
)
"""


def initialize_policy_tables() -> None:
    conn = connect()
    conn.execute(POLICY_SCHEMA)
    conn.execute(DECISION_SCHEMA)
    conn.commit()
    conn.close()


def _json(value):
    return json.dumps(value, sort_keys=True)


def _loads(value, default):
    try:
        return json.loads(value or "")
    except json.JSONDecodeError:
        return default


def _policy_from_row(row) -> dict[str, Any]:
    item = dict(row)
    item["enabled"] = bool(item["enabled"])
    item["conditions"] = _loads(item.get("conditions"), {})
    item["actions"] = _loads(item.get("actions"), [])
    return item


def _decision_from_row(row) -> dict[str, Any]:
    item = dict(row)
    item["matched"] = bool(item["matched"])
    item["allowed"] = bool(item["allowed"])
    item["dry_run"] = bool(item["dry_run"])
    return item


class PolicyEngine:
    def initialize(self) -> None:
        initialize_policy_tables()
        self.ensure_default_policies()

    def ensure_default_policies(self) -> None:
        conn = connect()
        for policy in default_policies():
            now = now_iso()
            existing = conn.execute("SELECT policy_id FROM policies WHERE policy_id = ?", (policy["policy_id"],)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE policies SET name = ?, description = ?, priority = ?, trigger_event_type = ?, conditions = ?, actions = ?, safety_level = ?, updated_at = ? WHERE policy_id = ?",
                    (
                        policy["name"],
                        policy["description"],
                        policy["priority"],
                        policy["trigger_event_type"],
                        _json(policy["conditions"]),
                        _json(policy["actions"]),
                        policy["safety_level"],
                        now,
                        policy["policy_id"],
                    ),
                )
            else:
                conn.execute(
                    "INSERT INTO policies (policy_id, name, description, enabled, priority, trigger_event_type, conditions, actions, safety_level, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        policy["policy_id"],
                        policy["name"],
                        policy["description"],
                        1 if policy.get("enabled", True) else 0,
                        policy["priority"],
                        policy["trigger_event_type"],
                        _json(policy["conditions"]),
                        _json(policy["actions"]),
                        policy["safety_level"],
                        now,
                        now,
                    ),
                )
        conn.commit()
        conn.close()

    def list_policies(self) -> list[dict[str, Any]]:
        conn = connect()
        rows = conn.execute("SELECT * FROM policies ORDER BY priority ASC, policy_id ASC").fetchall()
        conn.close()
        return [_policy_from_row(row) for row in rows]

    def get_policy(self, policy_id: str) -> dict[str, Any] | None:
        conn = connect()
        row = conn.execute("SELECT * FROM policies WHERE policy_id = ?", (policy_id,)).fetchone()
        conn.close()
        return _policy_from_row(row) if row else None

    def set_enabled(self, policy_id: str, enabled: bool) -> dict[str, Any] | None:
        conn = connect()
        conn.execute("UPDATE policies SET enabled = ?, updated_at = ? WHERE policy_id = ?", (1 if enabled else 0, now_iso(), policy_id))
        conn.commit()
        conn.close()
        return self.get_policy(policy_id)

    def list_decisions(self, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 1000))
        conn = connect()
        rows = conn.execute("SELECT * FROM policy_decisions ORDER BY timestamp DESC LIMIT ?", (safe_limit,)).fetchall()
        conn.close()
        return [_decision_from_row(row) for row in rows]

    def event_matches_policy(self, event: Event, policy: dict[str, Any]) -> bool:
        trigger = policy["trigger_event_type"]
        return trigger == event.type or (trigger.endswith(".*") and event.type.startswith(trigger[:-1]))

    def conditions_match(self, policy: dict[str, Any], event: Event, asset: dict[str, Any] | None) -> tuple[bool, str]:
        conditions = policy.get("conditions") or {}
        for key, expected in conditions.items():
            if key == "asset_id":
                actual = event.asset_id or event.service or event.payload.get("asset_id")
            else:
                actual = (asset or {}).get(key) or event.payload.get(key)
            if actual != expected:
                return False, f"Condition {key} expected {expected}, got {actual}."
        return True, "All policy conditions matched."

    def store_decision(self, decision: Decision) -> dict[str, Any]:
        data = decision.to_dict()
        conn = connect()
        conn.execute(
            "INSERT INTO policy_decisions (decision_id, policy_id, timestamp, asset_id, event_id, matched, allowed, action, reason, explanation, dry_run) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data["decision_id"],
                data["policy_id"],
                data["timestamp"],
                data["asset_id"],
                data["event_id"],
                1 if data["matched"] else 0,
                1 if data["allowed"] else 0,
                data["action"],
                data["reason"],
                data["explanation"],
                1 if data["dry_run"] else 0,
            ),
        )
        conn.commit()
        conn.close()
        return data

    def apply_action(self, action: dict[str, Any], event: Event, asset: dict[str, Any] | None) -> tuple[bool, str, str, bool]:
        action_type = action.get("type", "unknown")
        asset_id = event.asset_id or event.service or event.payload.get("asset_id")
        name = (asset or {}).get("name") or asset_id
        classification = (asset or {}).get("classification") or event.payload.get("classification") or "unknown"
        if action_type == "recommend_classification":
            create_recommendation("info", "policy", asset_id, f"Classify container {name}", f"Policy recommends classifying {asset_id} as critical, optional, or stopped-by-design.")
            return True, action_type, "Recommendation created; no automatic action allowed.", True
        if action_type == "create_critical_incident":
            create_critical_incident(asset_id, "Critical Docker asset stopped", f"{asset_id} is critical and is not running.")
            return True, action_type, "Critical incident created; no automatic restart allowed.", True
        if action_type == "recommend_manual_investigation":
            create_recommendation("critical", "policy", asset_id, f"Investigate critical asset {name}", f"{asset_id} matched critical stopped policy. Manual investigation required.")
            return True, action_type, "Critical recommendation created; restart denied by default.", True
        if action_type == "recommend_restart":
            create_recommendation("warning", "policy", asset_id, f"Consider restart for {name}", f"{asset_id} is optional and stopped. Policy recommends manual restart only.")
            return True, action_type, "Manual restart recommendation created; automatic restart denied.", True
        if action_type == "ignore":
            ignore()
            return True, action_type, f"Ignored because classification is {classification}.", True
        if action_type == "dependency_guard":
            dependency = action.get("dependency")
            required_state = action.get("required_state", "running")
            dependency_asset = asset_registry.get_asset(dependency) if dependency else None
            actual_state = (dependency_asset or {}).get("state")
            if actual_state != required_state:
                deny()
                return False, action_type, f"Denied future auto-start: dependency {dependency} must be {required_state}, got {actual_state}.", True
            return True, action_type, f"Dependency guard passed: {dependency} is {required_state}. No action executed.", True
        return False, action_type, "Unknown policy action denied.", True

    def evaluate_event(self, event: Event) -> list[dict[str, Any]]:
        decisions = []
        asset_id = event.asset_id or event.service or event.payload.get("asset_id")
        asset = asset_registry.get_asset(asset_id) if asset_id else None
        for policy in self.list_policies():
            if not policy["enabled"] or not self.event_matches_policy(event, policy):
                continue
            matched, reason = self.conditions_match(policy, event, asset)
            if not matched:
                explanation = explain_match(policy, event, asset, False, False, "none", reason)
                decisions.append(self.store_decision(Decision(policy["policy_id"], asset_id, event.id, False, False, "none", reason, explanation, True)))
                continue
            for action in policy.get("actions", []):
                allowed, action_name, action_reason, dry_run = self.apply_action(action, event, asset)
                explanation = explain_match(policy, event, asset, True, allowed, action_name, action_reason)
                decisions.append(self.store_decision(Decision(policy["policy_id"], asset_id, event.id, True, allowed, action_name, action_reason, explanation, dry_run)))
        return decisions

    def on_event(self, event: Event) -> None:
        if event.source == "policy_engine":
            return
        try:
            self.evaluate_event(event)
        except Exception:
            # Policy errors must never crash the event bus or worker.
            return


policy_engine = PolicyEngine()
