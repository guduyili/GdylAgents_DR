from __future__ import annotations

from models import SummaryState, TodoItem
from services.review_service import ReviewService
from services.stream_runner import StreamRunner


class FakePlanner:
    def plan_todo_list(self, state: SummaryState) -> list[TodoItem]:
        raise AssertionError("quick mode should not call planner")

    def create_fallback_task(self, state: SummaryState) -> TodoItem:
        return TodoItem(id=99, title="兜底", intent="兜底", query=state.research_topic)


class FakeTaskExecutor:
    def execute(self, state: SummaryState, task: TodoItem, *, emit_stream: bool, step: int | None = None):
        task.summary = "快速摘要内容"
        task.sources_summary = "来源 A"
        task.status = "completed"
        yield {"type": "sources", "task_id": task.id, "latest_sources": "来源 A", "backend": "duckduckgo"}
        yield {"type": "task_status", "task_id": task.id, "status": "completed", "summary": "快速摘要内容"}


class FakeReporting:
    def generate_report(self, state: SummaryState) -> str:
        raise AssertionError("quick mode should not call full report generator")


def serialize_task(task: TodoItem) -> dict:
    return {"id": task.id, "title": task.title, "intent": task.intent, "status": task.status}


def test_stream_runner_quick_mode_skips_planner_and_emits_single_task_report() -> None:
    runner = StreamRunner(
        planner=FakePlanner(),
        task_executor=FakeTaskExecutor(),
        reporting=FakeReporting(),
        drain_tool_events=lambda state, step=None: [],
        set_tool_event_sink=lambda sink: None,
        persist_final_report=lambda state, report: None,
        serialize_task=serialize_task,
        research_mode="quick",
        review_service=ReviewService(min_report_chars=10),
        enable_report_review=True,
    )

    events = list(runner.run("AI Agent 快速浏览"))

    todo_lists = [event for event in events if event["type"] == "todo_list"]
    assert len(todo_lists) == 1
    assert len(todo_lists[0]["tasks"]) == 1
    assert todo_lists[0]["tasks"][0]["title"].startswith("快速浏览：")

    final_reports = [event for event in events if event["type"] == "final_report"]
    assert final_reports
    assert "快速摘要内容" in final_reports[0]["report"]
    assert final_reports[0]["source"] == "stream_runner"

    review_events = [event for event in events if event["type"] == "review_result"]
    assert len(review_events) == 1
    assert review_events[0]["source"] == "review_service"
    assert events[-1]["type"] == "done"