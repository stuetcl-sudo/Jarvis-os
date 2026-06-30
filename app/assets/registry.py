import json
from typing import Any

from app.assets.asset import Asset, now_iso
from app.db import connect

ASSET_SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    asset_type TEXT NOT NULL,
    plugin TEXT NOT NULL,
    name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    state TEXT NOT NULL,
    health TEXT,
    classification TEXT NOT NULL,
    protected INTEGER NOT NULL DEFAULT 0,
    auto_actions_allowed INTEGER NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def initialize_asset_tables() -> None:
    conn = connect()
    conn.execute(ASSET_SCHEMA)
    conn.commit()
    conn.close()


def _row_to_asset(row) -> dict[str, Any]:
    item = dict(row)
    try:
        item["metadata"] = json.loads(item.get("metadata") or "{}")
    except json.JSONDecodeError:
        item["metadata"] = {}
    item["protected"] = bool(item["protected"])
    item["auto_actions_allowed"] = bool(item["auto_actions_allowed"])
    return item


class AssetRegistry:
    def register_asset(self, asset: Asset | dict[str, Any]) -> dict[str, Any]:
        data = asset.to_dict() if hasattr(asset, "to_dict") else dict(asset)
        now = now_iso()
        data.setdefault("created_at", now)
        data["updated_at"] = now
        conn = connect()
        existing = conn.execute("SELECT asset_id, created_at FROM assets WHERE asset_id = ?", (data["asset_id"],)).fetchone()
        created_at = existing["created_at"] if existing else data["created_at"]
        conn.execute(
            """
            INSERT INTO assets (asset_id, asset_type, plugin, name, display_name, state, health, classification, protected, auto_actions_allowed, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET
                asset_type = excluded.asset_type,
                plugin = excluded.plugin,
                name = excluded.name,
                display_name = excluded.display_name,
                state = excluded.state,
                health = excluded.health,
                classification = excluded.classification,
                protected = excluded.protected,
                auto_actions_allowed = excluded.auto_actions_allowed,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at
            """,
            (
                data["asset_id"],
                data["asset_type"],
                data["plugin"],
                data["name"],
                data.get("display_name") or data["name"],
                data.get("state", "unknown"),
                data.get("health"),
                data.get("classification", "unknown"),
                1 if data.get("protected") else 0,
                1 if data.get("auto_actions_allowed") else 0,
                json.dumps(data.get("metadata", {}), sort_keys=True),
                created_at,
                data["updated_at"],
            ),
        )
        conn.commit()
        conn.close()
        return self.get_asset(data["asset_id"])

    def update_asset(self, asset_id: str, **changes: Any) -> dict[str, Any] | None:
        existing = self.get_asset(asset_id)
        if not existing:
            return None
        existing.update(changes)
        existing["asset_id"] = asset_id
        return self.register_asset(existing)

    def remove_asset(self, asset_id: str) -> bool:
        conn = connect()
        cur = conn.execute("DELETE FROM assets WHERE asset_id = ?", (asset_id,))
        conn.commit()
        changed = cur.rowcount > 0
        conn.close()
        return changed

    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        conn = connect()
        row = conn.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        conn.close()
        return _row_to_asset(row) if row else None

    def list_assets(self, plugin: str | None = None, asset_type: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if plugin:
            clauses.append("plugin = ?")
            params.append(plugin)
        if asset_type:
            clauses.append("asset_type = ?")
            params.append(asset_type)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(int(limit), 2000)))
        conn = connect()
        rows = conn.execute(f"SELECT * FROM assets{where} ORDER BY plugin ASC, display_name ASC LIMIT ?", tuple(params)).fetchall()
        conn.close()
        return [_row_to_asset(row) for row in rows]

    def search_assets(self, query: str, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        q = f"%{query}%"
        conn = connect()
        rows = conn.execute(
            """
            SELECT * FROM assets
            WHERE asset_id LIKE ? OR name LIKE ? OR display_name LIKE ? OR plugin LIKE ? OR asset_type LIKE ? OR classification LIKE ?
            ORDER BY plugin ASC, display_name ASC
            LIMIT ?
            """,
            (q, q, q, q, q, q, safe_limit),
        ).fetchall()
        conn.close()
        return [_row_to_asset(row) for row in rows]


asset_registry = AssetRegistry()
