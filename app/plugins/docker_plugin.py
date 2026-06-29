from typing import Any

from app.docker_monitor import list_containers
from app.plugins.base import JarvisPlugin


class DockerPlugin(JarvisPlugin):
    name = "docker"
    description = "Read-only Docker container inventory plugin"

    def collect(self) -> dict[str, Any]:
        containers, error = list_containers()
        return {
            "plugin": self.name,
            "error": error,
            "containers": containers,
        }
