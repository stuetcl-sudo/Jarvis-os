from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Policy:
    policy_id: str
    name: str
    description: str
    enabled: bool
    priority: int
    trigger_event_type: str
    conditions: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    safety_level: str = "safe_observation"
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Decision:
    policy_id: str
    asset_id: str | None
    event_id: str | None
    matched: bool
    allowed: bool
    action: str
    reason: str
    explanation: str
    dry_run: bool = True
    decision_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
