from app.assets.asset import Asset
from app.assets.registry import asset_registry
from app.assets.types import AssetTypes


def register_system_health_assets(health: dict) -> None:
    resources = [
        ("system:cpu", "cpu", "CPU", health.get("cpu_percent"), None),
        ("system:memory", "memory", "Memory", health.get("memory", {}).get("percent"), None),
        ("system:swap", "swap", "Swap", health.get("swap", {}).get("percent"), None),
        ("system:disk", "disk", "Root Disk", health.get("disk_root", {}).get("percent"), None),
    ]
    for asset_id, name, display_name, percent, health_status in resources:
        state = "unknown" if percent is None else f"{float(percent):.1f}%"
        asset_registry.register_asset(
            Asset(
                asset_id=asset_id,
                asset_type=AssetTypes.SYSTEM_RESOURCE,
                plugin="system",
                name=name,
                display_name=display_name,
                state=state,
                health=health_status,
                classification="critical",
                protected=True,
                auto_actions_allowed=False,
                metadata={"percent": percent},
            )
        )
