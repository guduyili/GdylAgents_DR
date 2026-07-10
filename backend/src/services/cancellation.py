"""Research run cancellation helpers."""

from __future__ import annotations

from threading import Event
from typing import Protocol


class StopSignal(Protocol):
    def is_set(self) -> bool: ...


class ResearchCancelled(Exception):
    """Raised when a research run is cancelled while work is in progress."""


def is_cancelled(stop_event: StopSignal | Event | None) -> bool:
    """Return True when the shared stop event has been requested."""
    return stop_event is not None and stop_event.is_set()


def ensure_not_cancelled(stop_event: StopSignal | Event | None) -> None:
    """Raise ResearchCancelled when cancellation has been requested."""
    if is_cancelled(stop_event):
        raise ResearchCancelled("研究已取消")