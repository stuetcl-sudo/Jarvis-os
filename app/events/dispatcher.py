from app.events.bus import event_bus
from app.events.event import Event


def publish(source: str, event_type: str, severity: str = "info", service: str | None = None, payload: dict | None = None, asset_id: str | None = None) -> Event:
    payload = payload or {}
    resolved_asset_id = asset_id or payload.get("asset_id") or (service if isinstance(service, str) and ":" in service else None)
    event = Event(
        source=source,
        type=event_type,
        severity=severity,
        service=service,
        asset_id=resolved_asset_id,
        payload=payload,
    )
    return event_bus.publish(event)
