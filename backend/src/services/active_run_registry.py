"""In-memory registry mapping active research run_id to cancellation events."""

from __future__ import annotations

from threading import Event, Lock


class ActiveRunRegistry:
    """Track stop_event handles for runs that are still executing."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._runs: dict[str, Event] = {}

    def register(self, run_id: str, stop_event: Event) -> None:
        with self._lock:
            self._runs[run_id] = stop_event

    def unregister(self, run_id: str) -> None:
        with self._lock:
            self._runs.pop(run_id, None)

    def request_cancel(self, run_id: str) -> bool:
        with self._lock:
            stop_event = self._runs.get(run_id)
        if stop_event is None:
            return False
        stop_event.set()
        return True

    def is_active(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._runs