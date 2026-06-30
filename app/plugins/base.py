from abc import ABC
from typing import Any

from app.events.dispatcher import publish as publish_event
from app.events.event import Event


class PluginBase(ABC):
    """Safe event-driven plugin base.

    Plugins may publish and handle events, but must not run arbitrary system
    commands or perform destructive actions directly.
    """

    name: str = "base"
    description: str = "Base Jarvis plugin"

    def initialize(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def register(self) -> None:
        pass

    def on_event(self, event: Event) -> None:
        pass

    def publish(self, event_type: str, severity: str = "info", service: str | None = None, payload: dict[str, Any] | None = None, asset_id: str | None = None) -> Event:
        payload = payload or {}
        return publish_event(self.name, event_type, severity, service, payload, asset_id=asset_id)

    def collect(self) -> dict[str, Any]:
        return {}


JarvisPlugin = PluginBase
