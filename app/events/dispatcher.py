from app.events.bus import event_bus
from app.events.event import Event


def publish(source: str, event_type: str, severity: str = "info", service: str | None = None, payload: dict | None = None) -> Event:
    event = Event(
        source=source,
        type=event_type,
        severity=severity,
        service=service,
        payload=payload or {},
    )
    return event_bus.publish(event)
