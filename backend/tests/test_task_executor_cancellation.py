from __future__ import annotations

import time
from threading import Event, Lock, Thread

from config import Configuration, SearchAPI
from models import SummaryState, TodoItem
from services.task_executor import TaskExecutor


class BlockingSummarizer:
    def stream_task_summary(self, state: SummaryState, task: TodoItem, context: str):
        def generator():
            for _ in range(50):
                time.sleep(0.05)
                yield "chunk"

        return generator(), lambda: "summary"

    def summarize_task(self, state: SummaryState, task: TodoItem, context: str) -> str:
        return "summary"


def test_task_executor_stops_during_search_when_cancelled() -> None:
    stop_event = Event()
    config = Configuration(
        search_api=SearchAPI.DUCKDUCKGO,
        search_timeout_seconds=5,
        summary_timeout_seconds=5,
    )
    state = SummaryState(research_topic="topic")
    task = TodoItem(id=1, title="任务", intent="目标", query="topic")

    def slow_search(query: str, cfg: Configuration, loop_count: int):
        time.sleep(2)
        return {"results": [{"title": "t", "url": "https://example.com"}]}, [], None, "duckduckgo"

    executor = TaskExecutor(
        config=config,
        summarizer=BlockingSummarizer(),
        state_lock=Lock(),
        drain_tool_events=lambda state, step=None: [],
        search_dispatcher=slow_search,
    )

    def cancel_later() -> None:
        time.sleep(0.3)
        stop_event.set()

    Thread(target=cancel_later, daemon=True).start()

    events = list(executor.execute(state, task, emit_stream=True, stop_event=stop_event))

    assert events
    assert events[-1]["type"] == "task_status"
    assert events[-1]["status"] == "cancelled"
    assert task.status == "cancelled"