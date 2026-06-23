from __future__ import annotations

from collections.abc import Iterator
from threading import Lock

from config import Configuration, SearchAPI
from models import SummaryState, TodoItem
from services.stream_runner import StreamRunner
from services.task_executor import TaskExecutor
from services.tool_events import ToolCallTracker


class FakePlanner:
    def plan_todo_list(self, state: SummaryState) -> list[TodoItem]:
        return []

    def create_fallback_task(self, state: SummaryState) -> TodoItem:
        return TodoItem(id=99, title="兜底任务", intent="兜底", query=state.research_topic)


class FakeTaskExecutor:
    def execute(self, state: SummaryState, task: TodoItem, *, emit_stream: bool, step: int | None = None) -> Iterator[dict]:
        yield {"type": "sources", "task_id": task.id, "latest_sources": "S", "backend": "duckduckgo"}
        task.summary = "任务摘要"
        task.status = "completed"
        yield {"type": "task_status", "task_id": task.id, "status": "completed", "summary": "任务摘要"}


class FakeReporting:
    def generate_report(self, state: SummaryState) -> str:
        return "最终报告"


def serialize_task(task: TodoItem) -> dict:
    return {"id": task.id, "title": task.title, "intent": task.intent, "status": task.status, "stream_token": task.stream_token}


def test_stream_runner_emits_source_and_duration_for_traceable_events() -> None:
    task = TodoItem(id=1, title="任务一", intent="研究", query="agent")
    ticks = iter([index * 0.01 for index in range(40)])
    runner = StreamRunner(
        planner=FakePlanner(),
        task_executor=FakeTaskExecutor(),
        reporting=FakeReporting(),
        drain_tool_events=lambda state, step=None: [],
        set_tool_event_sink=lambda sink: None,
        persist_final_report=lambda state, report: None,
        serialize_task=serialize_task,
        run_id_factory=lambda: "run-observe-001",
        clock=lambda: "2026-06-12T00:00:00Z",
        monotonic_clock=lambda: next(ticks),
    )

    events = list(runner.run("AI Agent", todo_items=[task]))

    assert next(event for event in events if event["type"] == "status")["source"] == "stream_runner"
    assert next(event for event in events if event["type"] == "todo_list")["source"] == "stream_runner"
    sources = next(event for event in events if event["type"] == "sources")
    completed = next(
        event for event in events if event["type"] == "task_status" and event.get("status") == "completed"
    )
    assert sources["source"] == "task_executor"
    assert sources["duration_ms"] >= 0
    assert completed["source"] == "task_executor"
    assert completed["duration_ms"] >= 0
    assert next(event for event in events if event["type"] == "final_report")["source"] == "reporter"
    assert next(event for event in events if event["type"] == "done")["source"] == "stream_runner"
    assert any(event["type"] == "phase_duration" and event.get("phase") == "search" for event in events)


def test_task_executor_stream_events_include_source_backend_and_duration() -> None:
    state = SummaryState(research_topic="AI Agent")
    task = TodoItem(id=1, title="任务一", intent="研究", query="agent research")

    class FakeSummarizer:
        def stream_task_summary(self, state: SummaryState, task: TodoItem, context: str):
            def chunks():
                yield "摘要"
            return chunks(), lambda: "摘要"

    def fake_dispatch(query: str, config: Configuration, loop_count: int):
        return {"results": [{"title": "A", "url": "https://example.com"}]}, [], "answer", "duckduckgo"

    executor = TaskExecutor(
        config=Configuration(search_api=SearchAPI.DUCKDUCKGO, enable_notes=False),
        summarizer=FakeSummarizer(),
        state_lock=Lock(),
        drain_tool_events=lambda state, step=None: [],
        search_dispatcher=fake_dispatch,
        context_preparer=lambda search_result, answer_text, config: ("来源", "上下文"),
        monotonic_clock=lambda: 1.0,
    )

    events = list(executor.execute(state, task, emit_stream=True, step=1))

    sources = next(event for event in events if event["type"] == "sources")
    completed = next(event for event in events if event["type"] == "task_status")
    chunk = next(event for event in events if event["type"] == "task_summary_chunk")

    assert sources["source"] == "task_executor"
    assert sources["backend"] == "duckduckgo"
    assert sources["duration_ms"] >= 0
    assert chunk["source"] == "summarizer"
    assert completed["source"] == "task_executor"
    assert completed["duration_ms"] >= 0


def test_tool_call_tracker_payload_includes_source_and_duration() -> None:
    tracker = ToolCallTracker(notes_workspace=None, monotonic_clock=lambda: 2.0)
    tracker.record(
        {
            "agent_name": "Researcher",
            "tool_name": "note",
            "raw_parameters": "{}",
            "parsed_parameters": {"task_id": 1},
            "result": "OK",
        }
    )

    payload = tracker.drain(SummaryState(research_topic="AI Agent"), step=1)[0]

    assert payload["type"] == "tool_call"
    assert payload["source"] == "tool"
    assert payload["duration_ms"] >= 0
