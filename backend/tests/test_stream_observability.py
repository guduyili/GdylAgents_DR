from __future__ import annotations

from models import SummaryState, TodoItem
from services.stream_runner import StreamRunner


class FakePlanner:
    def plan_todo_list(self, state: SummaryState) -> list[TodoItem]:
        return []

    def create_fallback_task(self, state: SummaryState) -> TodoItem:
        return TodoItem(id=99, title="兜底任务", intent="兜底", query=state.research_topic)


class FakeTaskExecutor:
    def execute(self, state: SummaryState, task: TodoItem, *, emit_stream: bool, step: int | None = None):
        yield {"type": "tool_call", "event_id": 1, "task_id": task.id, "agent": "A", "tool": "note"}


class FakeReporting:
    def generate_report(self, state: SummaryState) -> str:
        return "最终报告"


def serialize_task(task: TodoItem) -> dict:
    return {"id": task.id, "title": task.title, "intent": task.intent, "status": task.status}


def test_stream_runner_adds_same_run_id_and_timestamp_to_all_public_events() -> None:
    task = TodoItem(id=1, title="任务一", intent="研究", query="agent")
    runner = StreamRunner(
        planner=FakePlanner(),
        task_executor=FakeTaskExecutor(),
        reporting=FakeReporting(),
        drain_tool_events=lambda state, step=None: [],
        set_tool_event_sink=lambda sink: None,
        persist_final_report=lambda state, report: None,
        serialize_task=serialize_task,
        run_id_factory=lambda: "run-test-001",
        clock=lambda: "2026-06-05T12:00:00Z",
    )

    events = list(runner.run("AI Agent", todo_items=[task]))

    assert events
    assert {event["run_id"] for event in events} == {"run-test-001"}
    assert {event["timestamp"] for event in events} == {"2026-06-05T12:00:00Z"}
    assert all(event["type"] != "__task_done__" for event in events)


def test_stream_runner_enriches_tool_events_with_run_id_timestamp_and_task_channel() -> None:
    task = TodoItem(id=1, title="任务一", intent="研究", query="agent")
    runner = StreamRunner(
        planner=FakePlanner(),
        task_executor=FakeTaskExecutor(),
        reporting=FakeReporting(),
        drain_tool_events=lambda state, step=None: [],
        set_tool_event_sink=lambda sink: None,
        persist_final_report=lambda state, report: None,
        serialize_task=serialize_task,
        run_id_factory=lambda: "run-test-002",
        clock=lambda: "2026-06-05T12:00:01Z",
    )

    events = list(runner.run("AI Agent", todo_items=[task]))
    tool_events = [event for event in events if event["type"] == "tool_call"]

    assert tool_events == [
        {
            "type": "tool_call",
            "event_id": 1,
            "task_id": 1,
            "agent": "A",
            "tool": "note",
            "task_run_id": "run-test-002:task:1",
            "step": 1,
            "stream_token": "task_1",
            "run_id": "run-test-002",
            "timestamp": "2026-06-05T12:00:01Z",
            "source": "tool",
        }
    ]
