"""Research run cancellation helpers."""

from __future__ import annotations

from threading import Event
from typing import Protocol


class StopSignal(Protocol):
    def is_set(self) -> bool: ...


class ScopedStopSignal:
    """Combine a parent signal with a local stop without modifying the parent."""

    def __init__(self, parent: StopSignal | None = None) -> None:
        self._parent = parent
        self._local = Event()

    def set(self) -> None:
        self._local.set()

    def is_set(self) -> bool:
        return self._local.is_set() or (
            self._parent is not None and self._parent.is_set()
        )


class ResearchCancelled(Exception):
    """Raised when a research run is cancelled while work is in progress."""


def is_cancelled(stop_event: StopSignal | Event | None) -> bool:
    """Return True when the shared stop event has been requested."""
    return stop_event is not None and stop_event.is_set()


def ensure_not_cancelled(stop_event: StopSignal | Event | None) -> None:
    """Raise ResearchCancelled when cancellation has been requested."""
    if is_cancelled(stop_event):
        raise ResearchCancelled("研究已取消")
