"""工具事件桥：封装 ToolCallTracker 的实时 sink 与 drain 策略。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from models import SummaryState


class ToolTrackerLike(Protocol):
    def set_event_sink(self, sink: Callable[[dict[str, Any]], None] | None) -> None: ...

    def drain(self, state: SummaryState, *, step: int | None = None) -> list[dict[str, Any]]: ...

    def as_dicts(self) -> list[dict[str, Any]]: ...


class ToolEventBridge:
    """管理工具事件在同步模式和流式模式下的消费方式。"""

    def __init__(self, *, tracker: ToolTrackerLike) -> None:
        self._tracker = tracker
        self._sink_enabled = False

    def set_sink(self, sink: Callable[[dict[str, Any]], None] | None) -> None:
        self._sink_enabled = sink is not None
        self._tracker.set_event_sink(sink)

    def drain(self, state: SummaryState, *, step: int | None = None) -> list[dict[str, Any]]:
        events = self._tracker.drain(state, step=step)
        if self._sink_enabled:
            return []
        return events

    def as_dicts(self) -> list[dict[str, Any]]:
        return self._tracker.as_dicts()
