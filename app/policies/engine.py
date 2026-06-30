import hashlib
import json
from typing import Any

from app.assets.registry import asset_registry
from app.db import connect
from app.events.event import Event
from app.policies.actions import create_critical_incident, create_recommendation, deny, ignore
from app.policies.explain import explain_match
from app.policies.policy import Decision, now_iso
from app.policies.rules import default_policies

POLICY_SEED_VERSION = 2
JARVIS_MANAGED_BY = "jarvis"

# Canonical SHA-256 fingerprints derived from the exact default_policies()
# implementation at feature/policy-engine. Enabled state is intentionally excluded.
HISTORICAL_POLICY_FINGERPRINTS = frozenset(
    {
        "1986aa84ce387ff4d16cf21a526dfadbe117188f81110aba8b262b40f6e9e2e1",
        "7dcbad131373e9c39fcc6a64962d076a00c3c773caad9eae5b66f42aa7166663",
        "acaef0f17676f39a30b276850ea9633c152871dfe377299e95c582a7ad043a3e",
        "b83998771fc32288733b45e4ff846d96bcc5ed6904173bc0fa97fc804bf56f40",
        "bfaea0c29c67521d9ecdbfcb4e59ee9ad5d1914951f6ddb5e81783c1bbe0ec5d",
    }
)

# Policy-id-only fingerprints allow already managed obsolete rows to be retired
# without retaining historical deployment-specific identifiers in tracked source.
OBSOLETE_MANAGED_POLICY_ID_FINGERPRINTS = frozenset(
    {
        "53da18ea4335624d28353d02ba56cb395b2d6bc860234e0682237e01b6d23c27",
        "73924beab8c4c73fdaf21205b08671dd2ba19ebaf2123bc139efadfcd9e5e942",
        "76680c1b8a6ab828529edc7f306460d0e865aa3141f8b9b2c251eb953cc36e17",
        "d89629288646143f6fb3ccd91279c854efabf48365cd2a3aaa34eee62ce9b931",
        "ec3a92794006c8edca2057f53033f13dd98896b9fac1b6100254ec980834d10f",
    }
)

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


def _columns(conn, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_column(conn, table: str, column: str, definition: str) -> None:
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialize_policy_tables() -> None:
    conn = connect()
    conn.execute(POLICY_SCHEMA)
    conn.execute(DECISION_SCHEMA)
    _ensure_column(conn, "policies", "managed_by", "TEXT")
    _ensure_column(conn, "policies", "seed_version", "INTEGER")
    _ensure_column(conn, "policies", "retired", "INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    conn.close()


def _json(value):
    return json.dumps(value, sort_keys=True)


def _loads(value, default):
    try:
        return json.loads(value or "")
    except json.JSONDecodeError:
        return default


def _stable_policy_view(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_id": policy["policy_id"],
        "name": policy["name"],
        "description": policy["description"],
        "priority": int(policy["priority"]),
        "trigger_event_type": policy["trigger_event_type"],
        "conditions": policy.get("conditions", {}),
        "actions": policy.get("actions", []),
        "safety_level": policy["safety_level"],
    }


def _stable_row_view(row) -> dict[str, Any]:
    item = dict(row)
    return {
        "policy_id": item["policy_id"],
        "name": item["name"],
        "description": item["description"],
        "priority": int(item["priority"]),
        "trigger_event_type": item["trigger_event_type"],
        "conditions": _loads(item.get("conditions"), {}),
        "actions": _loads(item.get("actions"), []),
        "safety_level": item["safety_level"],
    }


def _policy_fingerprint(policy: dict[str, Any]) -> str:
    canonical = json.dumps(_stable_policy_view(policy), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _row_policy_fingerprint(row) -> str:
    canonical = json.dumps(_stable_row_view(row), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _policy_id_fingerprint(policy_id: str) -> str:
    return hashlib.sha256(policy_id.encode("utf-8")).hexdigest()


def _policy_from_row(row) -> dict[str, Any]:
    item = dict(row)
    item["enabled"] = bool(item["enabled"])
    item["retired"] = bool(item.get("retired", 0))
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
        now = now_iso()
        current_seeds = default_policies()
        current_by_id = {policy["policy_id"]: policy for policy in current_seeds}
        current_fingerprints = {policy_id: _policy_fingerprint(policy) for policy_id, policy in current_by_id.items()}

        rows = conn.execute("SELECT * FROM policies").fetchall()
        for row in rows:
            policy_id = row["policy_id"]
            managed_by = row["managed_by"]
            if managed_by is None:
                fingerprint = _row_policy_fingerprint(row)
                if policy_id in current_fingerprints and fingerprint == current_fingerprints[policy_id]:
                    conn.execute(
                        "UPDATE policies SET managed_by = ?, seed_version = COALESCE(seed_version, ?) WHERE policy_id = ? AND managed_by IS NULL",
                        (JARVIS_MANAGED_BY, POLICY_SEED_VERSION, policy_id),
                    )
                elif fingerprint in HISTORICAL_POLICY_FINGERPRINTS:
                    conn.execute(
                        """
                        UPDATE policies
                        SET enabled = 0, retired = 1, managed_by = ?, seed_version = ?, updated_at = ?
                        WHERE policy_id = ? AND managed_by IS NULL
                        """,
                        (JARVIS_MANAGED_BY, POLICY_SEED_VERSION, now, policy_id),
                    )
            elif managed_by == JARVIS_MANAGED_BY and _policy_id_fingerprint(policy_id) in OBSOLETE_MANAGED_POLICY_ID_FINGERPRINTS:
                conn.execute(
                    "UPDATE policies SET enabled = 0, retired = 1, seed_version = ?, updated_at = ? WHERE policy_id = ? AND managed_by = ?",
                    (POLICY_SEED_VERSION, now, policy_id, JARVIS_MANAGED_BY),
                )

        for policy_id, policy in current_by_id.items():
            existing = conn.execute("SELECT * FROM policies WHERE policy_id = ?", (policy_id,)).fetchone()
            if existing and existing["managed_by"] == JARVIS_MANAGED_BY:
                conn.execute(
                    """
                    UPDATE policies
                    SET name = ?, description = ?, priority = ?, trigger_event_type = ?, conditions = ?, actions = ?, safety_level = ?, managed_by = ?, seed_version = ?, retired = 0, updated_at = ?
                    WHERE policy_id = ? AND managed_by = ?
                    """,
                    (
                        policy["name"],
                        policy["description"],
                        policy["priority"],
                        policy["trigger_event_type"],
                        _json(policy["conditions"]),
                        _json(policy["actions"]),
                        policy["safety_level"],
                        JARVIS_MANAGED_BY,
                        POLICY_SEED_VERSION,
                        now,
                        policy_id,
                        JARVIS_MANAGED_BY,
                    ),
                )
            elif not existing:
                conn.execute(
                    """
                    INSERT INTO policies (policy_id, name, description, enabled, priority, trigger_event_type, conditions, actions, safety_level, created_at, updated_at, managed_by, seed_version, retired)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        policy_id,
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
                        JARVIS_MANAGED_BY,
                        POLICY_SEED_VERSION,
                    ),
                )
        conn.commit()
        conn.close()

    def list_policies(self) -> list[dict[str, Any]]:
        conn = connect()
        rows = conn.execute("SELECT * FROM policies ORDER BY retired ASC, priority ASC, policy_id ASC").fetchall()
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
            actual = event.asset_id or event.service or event.payload.get("asset_id") if key == "asset_id" else (asset or {}).get(key) or event.payload.get(key)
            if actual != expected:
                return False, f"Condition {key} expected {expected}, got {actual}."
        return True, "All policy conditions matched."

    def store_decision(self, decision: Decision) -> dict[str, Any]:
        data = decision.to_dict()
        conn = connect()
        conn.execute(
            "INSERT INTO policy_decisions (decision_id, policy_id, timestamp, asset_id, event_id, matched, allowed, action, reason, explanation, dry_run) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (data["decision_id"], data["policy_id"], data["timestamp"], data["asset_id"], data["event_id"], 1 if data["matched"] else 0, 1 if data["allowed"] else 0, data["action"], data["reason"], data["explanation"], 1 if data["dry_run"] else 0),
        )
        conn.commit()
        conn.close()
        return data

    def apply_action(self, action: dict[str, Any], event: Event, asset: dict[str, Any] | None, policy: dict[str, Any]) -> tuple[bool, str, str, bool]:
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
        if action_type == "queue_manual_restart":
            return True, action_type, "Policy allowed a waiting-approval restart action to be queued after this decision is stored.", True
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

    def queue_action_for_decision(self, event: Event, asset_id: str | None, policy: dict[str, Any], decision: dict[str, Any]) -> None:
        if not asset_id or not decision.get("allowed"):
            return
        from app.actions.engine import action_engine
        action_engine.queue_action(
            asset_id=asset_id,
            action_type="docker.start_container",
            requested_by="policy",
            source="policy",
            reason=f"Policy queued manual restart for optional stopped asset {asset_id}.",
            requires_approval=True,
            payload={"event_id": event.id, "policy_id": policy["policy_id"], "policy_decision_id": decision["decision_id"]},
        )

    def evaluate_event(self, event: Event) -> list[dict[str, Any]]:
        decisions = []
        asset_id = event.asset_id or event.service or event.payload.get("asset_id")
        asset = asset_registry.get_asset(asset_id) if asset_id else None
        for policy in self.list_policies():
            if policy.get("retired") or not policy["enabled"] or not self.event_matches_policy(event, policy):
                continue
            matched, reason = self.conditions_match(policy, event, asset)
            if not matched:
                explanation = explain_match(policy, event, asset, False, False, "none", reason)
                decisions.append(self.store_decision(Decision(policy["policy_id"], asset_id, event.id, False, False, "none", reason, explanation, True)))
                continue
            for action in policy.get("actions", []):
                allowed, action_name, action_reason, dry_run = self.apply_action(action, event, asset, policy)
                explanation = explain_match(policy, event, asset, True, allowed, action_name, action_reason)
                decision = self.store_decision(Decision(policy["policy_id"], asset_id, event.id, True, allowed, action_name, action_reason, explanation, dry_run))
                decisions.append(decision)
                if action_name == "queue_manual_restart" and allowed:
                    try:
                        self.queue_action_for_decision(event, asset_id, policy, decision)
                    except Exception:
                        pass
        return decisions

    def on_event(self, event: Event) -> None:
        if event.source in {"policy_engine", "action_engine"}:
            return
        try:
            self.evaluate_event(event)
        except Exception:
            return


policy_engine = PolicyEngine()
