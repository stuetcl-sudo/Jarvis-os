from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


ACTION_STATUSES = {
    "queued",
    "waiting_approval",
    "approved",
    "running",
    "completed",
    "failed",
    "denied",
    "cancelled",
}

SUPPORTED_ACTION_TYPES = {
    "docker.start_container",
    "recommendation.create",
    "incident.create",
    "notification.create_stub",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Action:
    requested_by: str
    source: str
    asset_id: str
    action_type: str
    reason: str
    requires_approval: bool = True
    priority: int = 100
    payload: dict[str, Any] = field(default_factory=dict)
    action_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    status: str = "waiting_approval"
    approved: bool = False
    approved_by: str | None = None
    approved_at: str | None = None
    safety_status: str = "not_checked"
    explanation: str = "Queued action awaiting safety evaluation."
    result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
