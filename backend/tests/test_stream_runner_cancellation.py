from __future__ import annotations

import time
from threading import Event

from models import SummaryState, TodoItem
from services.research_run_store import InMemoryResearchRunStore
from services.stream_runner import StreamRunner


class FakePlanner:
    def plan_todo_list(self, state: SummaryState) -> list[TodoItem]:
        return []

    def create_fallback_task(self, state: SummaryState) -> TodoItem:
        return TodoItem(id=99, title="兜底", intent="兜底", query=state.research_topic)


class SlowTaskExecutor:
    def __init__(self, stop_event: Event) -> None:
        self._stop_event = stop_event
        self.calls = 0

    def execute(
        self,
        state: SummaryState,
        task: TodoItem,
        *,
        emit_stream: bool,
        step: int | None = None,
        stop_event: Event | None = None,
    ):
        self.calls += 1
        while not (stop_event and stop_event.is_set()):
            time.sleep(0.05)
        task.status = "cancelled"
        yield {
            "type": "task_status",
            "task_id": task.id,
            "status": "cancelled",
            "title": task.title,
            "intent": task.intent,
            "error": "任务已取消",
            "source": "task_executor",
        }


def serialize_task(task: TodoItem) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "intent": task.intent,
        "status": task.status,
    }


def test_stream_runner_emits_cancelled_and_marks_run_store_cancelled() -> None:
    stop_event = Event()
    task = TodoItem(id=1, title="任务一", intent="研究", query="agent")
    store = InMemoryResearchRunStore()
    executor = SlowTaskExecutor(stop_event)

    runner = StreamRunner(
        planner=FakePlanner(),
        task_executor=executor,
        reporting=object(),
        drain_tool_events=lambda state, step=None: [],
        set_tool_event_sink=lambda sink: None,
        persist_final_report=lambda state, report: None,
        serialize_task=serialize_task,
        run_store=store,
    )

    stream = runner.run("agent topic", todo_items=[task], stop_event=stop_event)
    events = []
    for event in stream:
        events.append(event)
        if event.get("type") == "todo_list":
            stop_event.set()

    event_types = [event["type"] for event in events]
    assert "cancelled" in event_types
    assert "final_report" not in event_types
    assert "done" not in event_types
    run_id = next(event["run_id"] for event in events if event.get("run_id"))
    assert store.get_run(run_id)["status"] == "cancelled"