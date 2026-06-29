from typing import Any

from app.assets.asset import now_iso
from app.assets.types import RelationshipTypes
from app.db import connect

RELATIONSHIP_SCHEMA = """
CREATE TABLE IF NOT EXISTS asset_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_asset_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    target_asset_id TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_asset_id, relationship_type, target_asset_id)
)
"""

VALID_RELATIONSHIPS = {
    RelationshipTypes.DEPENDS_ON,
    RelationshipTypes.CONTAINS,
    RelationshipTypes.CONNECTED_TO,
    RelationshipTypes.MANAGED_BY,
    RelationshipTypes.HOSTED_ON,
}


def initialize_relationship_tables() -> None:
    conn = connect()
    conn.execute(RELATIONSHIP_SCHEMA)
    conn.commit()
    conn.close()


def add_relationship(source_asset_id: str, relationship_type: str, target_asset_id: str, metadata: str = "{}") -> dict[str, Any]:
    if relationship_type not in VALID_RELATIONSHIPS:
        raise ValueError("Invalid relationship type")
    now = now_iso()
    conn = connect()
    conn.execute(
        """
        INSERT INTO asset_relationships (source_asset_id, relationship_type, target_asset_id, metadata, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_asset_id, relationship_type, target_asset_id) DO UPDATE SET
            metadata = excluded.metadata,
            updated_at = excluded.updated_at
        """,
        (source_asset_id, relationship_type, target_asset_id, metadata, now, now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM asset_relationships WHERE source_asset_id = ? AND relationship_type = ? AND target_asset_id = ?",
        (source_asset_id, relationship_type, target_asset_id),
    ).fetchone()
    conn.close()
    return dict(row)


def list_relationships(asset_id: str | None = None, relationship_type: str | None = None) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if asset_id:
        clauses.append("(source_asset_id = ? OR target_asset_id = ?)")
        params.extend([asset_id, asset_id])
    if relationship_type:
        clauses.append("relationship_type = ?")
        params.append(relationship_type)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    conn = connect()
    rows = conn.execute(f"SELECT * FROM asset_relationships{where} ORDER BY source_asset_id ASC, relationship_type ASC").fetchall()
    conn.close()
    return [dict(row) for row in rows]
