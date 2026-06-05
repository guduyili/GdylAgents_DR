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


class FakeRunStore:
    def __init__(self) -> None:
        self.started: list[dict] = []
        self.events: list[dict] = []
        self.completed: list[str] = []

    def start_run(self, *, run_id: str, topic: str) -> None:
        self.started.append({"run_id": run_id, "topic": topic})

    def record_event(self, run_id: str, event: dict) -> None:
        self.events.append({"run_id": run_id, "event": event})

    def complete_run(self, run_id: str) -> None:
        self.completed.append(run_id)


def serialize_task(task: TodoItem) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "intent": task.intent,
        "status": task.status,
        "task_run_id": task.task_run_id,
    }


def make_runner(run_store: FakeRunStore | None = None) -> StreamRunner:
    return StreamRunner(
        planner=FakePlanner(),
        task_executor=FakeTaskExecutor(),
        reporting=FakeReporting(),
        drain_tool_events=lambda state, step=None: [],
        set_tool_event_sink=lambda sink: None,
        persist_final_report=lambda state, report: None,
        serialize_task=serialize_task,
        run_id_factory=lambda: "run-test-001",
        clock=lambda: "2026-06-05T12:00:00Z",
        run_store=run_store,
    )


def test_stream_runner_assigns_stable_task_run_id_to_task_events() -> None:
    task = TodoItem(id=1, title="任务一", intent="研究", query="agent")

    events = list(make_runner().run("AI Agent", todo_items=[task]))

    assert task.task_run_id == "run-test-001:task:1"
    todo_event = next(event for event in events if event["type"] == "todo_list")
    assert todo_event["tasks"][0]["task_run_id"] == "run-test-001:task:1"
    task_events = [event for event in events if event.get("task_id") == 1]
    assert task_events
    assert {event["task_run_id"] for event in task_events} == {"run-test-001:task:1"}


def test_stream_runner_records_public_events_to_run_store() -> None:
    store = FakeRunStore()
    task = TodoItem(id=1, title="任务一", intent="研究", query="agent")

    events = list(make_runner(run_store=store).run("AI Agent", todo_items=[task]))

    assert store.started == [{"run_id": "run-test-001", "topic": "AI Agent"}]
    assert store.completed == ["run-test-001"]
    assert [item["event"] for item in store.events] == events
    assert all(item["run_id"] == "run-test-001" for item in store.events)
