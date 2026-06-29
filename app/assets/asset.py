from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Asset:
    asset_id: str
    asset_type: str
    plugin: str
    name: str
    display_name: str
    state: str = "unknown"
    health: str | None = None
    classification: str = "unknown"
    protected: bool = False
    auto_actions_allowed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
