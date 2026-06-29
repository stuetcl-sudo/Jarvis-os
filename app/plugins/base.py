from abc import ABC, abstractmethod
from typing import Any


class JarvisPlugin(ABC):
    """Read-only plugin interface prepared for Jarvis-os v0.4."""

    name: str = "base"
    description: str = "Base Jarvis plugin"

    @abstractmethod
    def collect(self) -> dict[str, Any]:
        """Collect plugin data without destructive side effects."""
        raise NotImplementedError
