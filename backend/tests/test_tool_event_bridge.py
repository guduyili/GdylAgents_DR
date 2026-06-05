from __future__ import annotations

from models import SummaryState, TodoItem
from services.tool_event_bridge import ToolEventBridge


class FakeTracker:
    def __init__(self) -> None:
        self.sinks = []
        self.events = [{"type": "tool_call", "task_id": 1}]

    def set_event_sink(self, sink):
        self.sinks.append(sink)

    def drain(self, state: SummaryState, *, step: int | None = None):
        return list(self.events)

    def as_dicts(self):
        return [{"type": "tool_call", "task_id": 1}]


def test_tool_event_bridge_suppresses_drain_when_sink_enabled() -> None:
    tracker = FakeTracker()
    bridge = ToolEventBridge(tracker=tracker)
    state = SummaryState(research_topic="AI Agent")

    assert bridge.drain(state) == [{"type": "tool_call", "task_id": 1}]

    sink = lambda event: None
    bridge.set_sink(sink)

    assert tracker.sinks[-1] is sink
    assert bridge.drain(state) == []

    bridge.set_sink(None)

    assert tracker.sinks[-1] is None
    assert bridge.drain(state) == [{"type": "tool_call", "task_id": 1}]


def test_tool_event_bridge_exposes_all_tool_call_events() -> None:
    bridge = ToolEventBridge(tracker=FakeTracker())

    assert bridge.as_dicts() == [{"type": "tool_call", "task_id": 1}]
