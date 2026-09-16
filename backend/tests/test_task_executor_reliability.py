from __future__ import annotations

import time
from threading import Event, Lock, Thread

import pytest

from config import Configuration, SearchAPI
from models import SummaryState, TodoItem
from services.task_executor import TaskExecutor


class SlowStreamSummarizer:
    def stream_task_summary(self, state: SummaryState, task: TodoItem, context: str):
        def generator():
            time.sleep(2)
            yield "摘要"

        return generator(), lambda: "摘要"


def make_config(**overrides) -> Configuration:
    base = {
        "search_api": SearchAPI.DUCKDUCKGO,
        "enable_notes": False,
    }
    base.update(overrides)
    return Configuration(**base)


def make_task() -> TodoItem:
    return TodoItem(id=1, title="任务一", intent="了解现状", query="agent research")


def test_execute_stream_fails_when_search_times_out() -> None:
    state = SummaryState(research_topic="AI Agent")
    task = make_task()

    def slow_dispatch(query: str, config: Configuration, loop_count: int):
        time.sleep(2)
        return {"results": [{"title": "A", "url": "https://example.com"}]}, [], None, "duckduckgo"

    executor = TaskExecutor(
        config=make_config(search_timeout_seconds=1),
        summarizer=SlowStreamSummarizer(),
        state_lock=Lock(),
        drain_tool_events=lambda state, step=None: [],
        search_dispatcher=slow_dispatch,
        context_preparer=lambda search_result, answer_text, config: ("", ""),
    )

    events = list(executor.execute(state, task, emit_stream=True, step=1))

    assert task.status == "failed"
    failed_events = [event for event in events if event.get("type") == "task_status" and event.get("status") == "failed"]
    assert len(failed_events) == 1
    assert "搜索超时" in failed_events[0]["error"]


def test_execute_stream_fails_when_summary_times_out() -> None:
    state = SummaryState(research_topic="AI Agent")
    task = make_task()

    def fast_dispatch(query: str, config: Configuration, loop_count: int):
        return {"results": [{"title": "A", "url": "https://example.com"}]}, [], None, "duckduckgo"

    executor = TaskExecutor(
        config=make_config(summary_timeout_seconds=1),
        summarizer=SlowStreamSummarizer(),
        state_lock=Lock(),
        drain_tool_events=lambda state, step=None: [],
        search_dispatcher=fast_dispatch,
        context_preparer=lambda search_result, answer_text, config: ("来源", "上下文"),
    )

    events = list(executor.execute(state, task, emit_stream=True, step=1))

    assert task.status == "failed"
    failed_events = [event for event in events if event.get("type") == "task_status" and event.get("status") == "failed"]
    assert len(failed_events) == 1
    assert "总结超时" in failed_events[0]["error"]


@pytest.mark.parametrize("cancel", [False, True], ids=["timeout", "cancel"])
def test_search_returns_before_blocked_operation_finishes(cancel: bool) -> None:
    started, release, finished, returned = Event(), Event(), Event(), Event()
    stop_event = Event()
    state = SummaryState(research_topic="AI Agent")
    task = make_task()
    events: list[dict] = []
    errors: list[Exception] = []

    def blocked_search(query, config, loop_count):
        started.set()
        try:
            release.wait(timeout=5)
            return {"results": [{"title": "Late", "url": "https://example.com"}]}, [], None, "duckduckgo"
        finally:
            finished.set()

    executor = TaskExecutor(
        config=make_config(search_timeout_seconds=30 if cancel else 1),
        summarizer=SlowStreamSummarizer(),
        state_lock=Lock(),
        drain_tool_events=lambda state, step=None: [],
        search_dispatcher=blocked_search,
    )

    def run():
        try:
            events.extend(executor.execute(state, task, emit_stream=True, stop_event=stop_event))
        except Exception as exc:
            errors.append(exc)
        finally:
            returned.set()

    caller = Thread(target=run, daemon=True)
    caller.start()
    expected_status = "cancelled" if cancel else "failed"
    try:
        assert started.wait(timeout=2), "Search did not start"
        if cancel:
            stop_event.set()
        assert returned.wait(timeout=2.5), "Caller waited for the blocked search to finish"
        assert not finished.is_set(), "Test must observe return before releasing the search"
        assert not errors
        assert task.status == expected_status
        terminal = [event for event in events if event["type"] == "task_status"]
        assert len(terminal) == 1
        assert terminal[0]["status"] == expected_status
        if not cancel:
            assert "搜索超时" in terminal[0]["error"]
    finally:
        release.set()
        caller.join(timeout=3)
        assert finished.wait(timeout=2), "Blocked search was not cleaned up"
        assert not caller.is_alive()

    assert task.status == expected_status
    assert all(event["type"] != "sources" for event in events)
