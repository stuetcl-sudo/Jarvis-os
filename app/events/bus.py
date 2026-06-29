from collections import deque
from threading import RLock
from typing import Callable

from app.events.event import Event

Listener = Callable[[Event], None]


class EventBus:
    def __init__(self, max_history: int = 1000):
        self._listeners: dict[str, list[Listener]] = {}
        self._history: deque[Event] = deque(maxlen=max_history)
        self._lock = RLock()

    def publish(self, event: Event) -> Event:
        with self._lock:
            self._history.appendleft(event)
            listeners = list(self._listeners.get(event.type, [])) + list(self._listeners.get("*", []))
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                # Listeners must never break the bus or worker.
                continue
        return event

    def subscribe(self, event_type: str, listener: Listener) -> None:
        with self._lock:
            self._listeners.setdefault(event_type, [])
            if listener not in self._listeners[event_type]:
                self._listeners[event_type].append(listener)

    def unsubscribe(self, event_type: str, listener: Listener) -> None:
        with self._lock:
            if event_type in self._listeners and listener in self._listeners[event_type]:
                self._listeners[event_type].remove(listener)

    def history(self, limit: int = 100) -> list[dict]:
        safe_limit = max(1, min(int(limit), 1000))
        with self._lock:
            return [event.to_dict() for event in list(self._history)[:safe_limit]]


event_bus = EventBus()
