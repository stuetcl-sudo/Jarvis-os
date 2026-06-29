from typing import Any

from app.health import get_health
from app.plugins.base import JarvisPlugin


class SystemPlugin(JarvisPlugin):
    name = "system"
    description = "Read-only system health plugin"

    def collect(self) -> dict[str, Any]:
        return {
            "plugin": self.name,
            "health": get_health(),
        }
