from __future__ import annotations

from threading import Lock

from config import Configuration, SearchAPI
from models import SummaryState, TodoItem
from services.task_executor import TaskExecutor


class StreamSummarizer:
    def stream_task_summary(self, state: SummaryState, task: TodoItem, context: str):
        def chunks():
            yield "摘要片段"

        return chunks(), lambda: "完整摘要"


def make_config() -> Configuration:
    return Configuration(search_api=SearchAPI.DUCKDUCKGO, enable_notes=False)


def make_task() -> TodoItem:
    return TodoItem(id=1, title="任务一", intent="了解现状", query="agent research")


def test_execute_stream_emits_tool_sources_chunk_and_completed_events() -> None:
    state = SummaryState(research_topic="AI Agent")
    task = make_task()
    tool_events = [
        {
            "type": "tool_call",
            "event_id": 7,
            "tool": "note",
            "agent": "研究专家",
            "task_id": 1,
            "source": "tool",
        }
    ]

    def fake_dispatch(query: str, config: Configuration, loop_count: int):
        return (
            {"results": [{"title": "A", "url": "https://example.com"}]},
            [],
            None,
            "duckduckgo",
        )

    executor = TaskExecutor(
        config=make_config(),
        summarizer=StreamSummarizer(),
        state_lock=Lock(),
        drain_tool_events=lambda state, step=None: tool_events,
        search_dispatcher=fake_dispatch,
        context_preparer=lambda search_result, answer_text, config: ("来源摘要", "上下文"),
    )

    events = list(executor.execute(state, task, emit_stream=True, step=1))
    event_types = [event["type"] for event in events]

    assert "tool_call" in event_types
    assert event_types.index("tool_call") < event_types.index("sources")
    assert "task_summary_chunk" in event_types
    assert event_types.index("sources") < event_types.index("task_summary_chunk")
    assert events[-1]["type"] == "task_status"
    assert events[-1]["status"] == "completed"
    assert task.summary == "完整摘要"