from __future__ import annotations

from models import SummaryState, TodoItem
from services.stream_runner import StreamRunner


class FakePlanner:
    def __init__(self, planned: list[TodoItem] | None = None) -> None:
        self.planned = planned or []
        self.plan_calls: list[SummaryState] = []

    def plan_todo_list(self, state: SummaryState) -> list[TodoItem]:
        self.plan_calls.append(state)
        return self.planned

    def create_fallback_task(self, state: SummaryState) -> TodoItem:
        return TodoItem(id=99, title="兜底任务", intent="兜底", query=state.research_topic)


class FakeTaskExecutor:
    def __init__(self, events: list[dict] | None = None, fail: Exception | None = None) -> None:
        self.events = events or []
        self.fail = fail
        self.calls: list[tuple[SummaryState, TodoItem, bool, int | None]] = []

    def execute(self, state: SummaryState, task: TodoItem, *, emit_stream: bool, step: int | None = None):
        self.calls.append((state, task, emit_stream, step))
        if self.fail:
            raise self.fail
        task.summary = "任务摘要"
        task.status = "completed"
        for event in self.events:
            yield dict(event)


class FakeReporting:
    def __init__(self, report: str = "最终报告") -> None:
        self.report = report
        self.calls: list[SummaryState] = []

    def generate_report(self, state: SummaryState) -> str:
        self.calls.append(state)
        return self.report


def serialize_task(task: TodoItem) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "intent": task.intent,
        "status": task.status,
        "summary": task.summary,
        "sources_summary": task.sources_summary,
        "notices": task.notices,
        "note_id": task.note_id,
        "note_path": task.note_path,
        "stream_token": task.stream_token,
    }


def make_task() -> TodoItem:
    return TodoItem(id=1, title="任务一", intent="研究", query="agent")


def test_stream_runner_runs_provided_tasks_and_emits_final_report() -> None:
    task = make_task()
    task_executor = FakeTaskExecutor(events=[{"type": "sources", "task_id": 1, "latest_sources": "S"}])
    reporting = FakeReporting("# 报告")
    sink_values: list[object] = []
    persisted: list[tuple[SummaryState, str]] = []

    runner = StreamRunner(
        planner=FakePlanner(),
        task_executor=task_executor,
        reporting=reporting,
        drain_tool_events=lambda state, step=None: [],
        set_tool_event_sink=sink_values.append,
        persist_final_report=lambda state, report: persisted.append((state, report)) or {"type": "report_note", "note_id": "n1"},
        serialize_task=serialize_task,
    )

    events = list(runner.run("AI Agent", todo_items=[task]))

    assert events[0]["type"] == "status"
    assert events[0]["message"] == "初始化研究流程"
    assert "run_id" in events[0]
    assert "timestamp" in events[0]
    assert events[1]["type"] == "todo_list"
    assert events[1]["tasks"][0]["stream_token"] == "task_1"
    assert {event["type"] for event in events} == {
        "status",
        "todo_list",
        "task_status",
        "sources",
        "report_note",
        "final_report",
        "done",
    }
    final_reports = [event for event in events if event.get("type") == "final_report"]
    assert final_reports
    assert final_reports[0]["report"] == "# 报告"
    assert final_reports[0]["note_id"] is None
    assert final_reports[0]["note_path"] is None
    assert "run_id" in final_reports[0]
    assert "timestamp" in final_reports[0]
    assert events[-1]["type"] == "done"
    assert "run_id" in events[-1]
    assert "timestamp" in events[-1]
    assert task_executor.calls[0][1] is task
    assert task_executor.calls[0][2] is True
    assert task_executor.calls[0][3] == 1
    assert reporting.calls
    assert persisted[0][1] == "# 报告"
    assert sink_values[0] is not None
    assert sink_values[-1] is None


def test_stream_runner_marks_task_failed_when_executor_raises() -> None:
    task = make_task()
    runner = StreamRunner(
        planner=FakePlanner(),
        task_executor=FakeTaskExecutor(fail=RuntimeError("boom")),
        reporting=FakeReporting("fallback-ready report"),
        drain_tool_events=lambda state, step=None: [],
        set_tool_event_sink=lambda sink: None,
        persist_final_report=lambda state, report: None,
        serialize_task=serialize_task,
    )

    events = list(runner.run("AI Agent", todo_items=[task]))

    failed_events = [event for event in events if event.get("type") == "task_status" and event.get("status") == "failed"]
    assert len(failed_events) == 1
    failed_event = failed_events[0]
    assert failed_event["type"] == "task_status"
    assert failed_event["task_id"] == 1
    assert failed_event["status"] == "failed"
    assert failed_event["error"] == "boom"
    assert failed_event["title"] == "任务一"
    assert failed_event["intent"] == "研究"
    assert failed_event["note_id"] is None
    assert failed_event["note_path"] is None
    assert failed_event["step"] == 1
    assert failed_event["stream_token"] == "task_1"
    assert "run_id" in failed_event
    assert "timestamp" in failed_event
    assert events[-1]["type"] == "done"
    assert "run_id" in events[-1]
    assert "timestamp" in events[-1]
