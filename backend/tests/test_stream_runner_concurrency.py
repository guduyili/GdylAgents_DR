from __future__ import annotations

import time
from queue import Queue
from threading import Event, Lock

import pytest

from models import SummaryState, TodoItem
from services.stream_runner import StreamRunner


class ConcurrentTrackingExecutor:
    def __init__(self, delay_seconds: float = 0.15) -> None:
        self.delay_seconds = delay_seconds
        self._lock = Lock()
        self.active_workers = 0
        self.max_active_workers = 0
        self.calls: list[int] = []

    def execute(self, state: SummaryState, task: TodoItem, *, emit_stream: bool, step: int | None = None, stop_event: Event | None = None):
        with self._lock:
            self.active_workers += 1
            self.max_active_workers = max(self.max_active_workers, self.active_workers)
            self.calls.append(task.id)

        try:
            time.sleep(self.delay_seconds)
            task.status = "completed"
            task.summary = "完成"
            yield {
                "type": "sources",
                "task_id": task.id,
                "latest_sources": "来源",
            }
        finally:
            with self._lock:
                self.active_workers -= 1


class FakePlanner:
    def plan_todo_list(self, state: SummaryState) -> list[TodoItem]:
        return []

    def create_fallback_task(self, state: SummaryState) -> TodoItem:
        return TodoItem(id=99, title="兜底", intent="兜底", query=state.research_topic)


class FakeReporting:
    def generate_report(self, state: SummaryState) -> str:
        return "报告"


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


def make_tasks(count: int) -> list[TodoItem]:
    return [
        TodoItem(id=index, title=f"任务{index}", intent="研究", query=f"topic-{index}")
        for index in range(1, count + 1)
    ]


def test_stream_runner_limits_concurrent_workers() -> None:
    task_executor = ConcurrentTrackingExecutor()
    runner = StreamRunner(
        planner=FakePlanner(),
        task_executor=task_executor,
        reporting=FakeReporting(),
        drain_tool_events=lambda state, step=None: [],
        set_tool_event_sink=lambda sink: None,
        persist_final_report=lambda state, report: None,
        serialize_task=serialize_task,
        max_concurrent_tasks=3,
    )

    events = list(runner.run("AI Agent", todo_items=make_tasks(10)))

    assert task_executor.max_active_workers <= 3
    assert len(task_executor.calls) == 10
    assert events[-1]["type"] == "done"


@pytest.mark.parametrize("failed_task_id", [None, 2], ids=["all-completed", "one-failed"])
def test_stream_runner_counts_all_queued_worker_completions(monkeypatch, failed_task_id) -> None:
    class InlinePool:
        """Queue every worker's events before the consumer starts."""

        def __init__(self, max_workers):
            pass

        def submit(self, fn, *args):
            fn(*args)

        def shutdown(self, **kwargs):
            pass

    class CompletionQueue(Queue):
        def get(self, block=True, timeout=None):
            if block and self.empty():
                raise AssertionError("All workers finished but completion notifications were lost")
            return super().get(block=block, timeout=timeout)

    class ScriptedExecutor(ConcurrentTrackingExecutor):
        def execute(self, state, task, *, emit_stream, step=None, stop_event=None):
            if task.id == failed_task_id:
                raise RuntimeError("worker failed")
            yield from super().execute(
                state, task, emit_stream=emit_stream, step=step, stop_event=stop_event
            )

    monkeypatch.setattr("services.stream_runner.ThreadPoolExecutor", InlinePool)
    monkeypatch.setattr("services.stream_runner.Queue", CompletionQueue)
    runner = StreamRunner(
        planner=FakePlanner(),
        task_executor=ScriptedExecutor(delay_seconds=0),
        reporting=FakeReporting(),
        drain_tool_events=lambda state, step=None: [],
        set_tool_event_sink=lambda sink: None,
        persist_final_report=lambda state, report: None,
        serialize_task=serialize_task,
    )

    events = list(runner.run("AI Agent", todo_items=make_tasks(3)))

    assert [event["task_id"] for event in events if event["type"] == "sources"] == [
        task_id for task_id in [1, 2, 3] if task_id != failed_task_id
    ]
    failures = [event for event in events if event.get("status") == "failed"]
    assert [event["task_id"] for event in failures] == ([] if failed_task_id is None else [2])
    if failures:
        assert failures[0]["error"] == "worker failed"
    assert sum(event["type"] == "final_report" for event in events) == 1
    assert sum(event["type"] == "done" for event in events) == 1
    assert events[-1]["type"] == "done"
    assert all(event["type"] != "__task_done__" for event in events)
