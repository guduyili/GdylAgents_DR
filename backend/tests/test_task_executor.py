from __future__ import annotations

from threading import Lock

from config import Configuration, SearchAPI
from models import SummaryState, TodoItem
from services.task_executor import TaskExecutor


class FakeSummarizer:
    def __init__(self, summary: str = "任务摘要") -> None:
        self.calls: list[tuple[SummaryState, TodoItem, str]] = []
        self.summary = summary

    def summarize_task(self, state: SummaryState, task: TodoItem, context: str) -> str:
        self.calls.append((state, task, context))
        return self.summary


def make_config() -> Configuration:
    return Configuration(search_api=SearchAPI.DUCKDUCKGO, enable_notes=False)


def make_task() -> TodoItem:
    return TodoItem(id=1, title="任务一", intent="了解现状", query="agent research")


def test_execute_sync_searches_prepares_context_summarizes_and_updates_state() -> None:
    state = SummaryState(research_topic="AI Agent")
    task = make_task()
    summarizer = FakeSummarizer("完成的摘要")

    def fake_dispatch(query: str, config: Configuration, loop_count: int):
        assert query == "agent research"
        assert loop_count == 0
        return {"results": [{"title": "A", "url": "https://example.com"}]}, ["搜索提示"], "直接答案", "duckduckgo"

    def fake_prepare(search_result, answer_text, config):
        assert answer_text == "直接答案"
        return "来源摘要", "完整上下文"

    executor = TaskExecutor(
        config=make_config(),
        summarizer=summarizer,
        state_lock=Lock(),
        drain_tool_events=lambda state, step=None: [],
        search_dispatcher=fake_dispatch,
        context_preparer=fake_prepare,
    )

    events = list(executor.execute(state, task, emit_stream=False))

    assert events == []
    assert task.status == "completed"
    assert task.notices == ["搜索提示"]
    assert task.sources_summary == "来源摘要"
    assert task.summary == "完成的摘要"
    assert state.web_research_results == ["完整上下文"]
    assert state.sources_gathered == ["来源摘要"]
    assert state.research_loop_count == 1
    assert summarizer.calls == [(state, task, "完整上下文")]


def test_execute_stream_skips_task_when_search_has_no_results() -> None:
    state = SummaryState(research_topic="AI Agent")
    task = make_task()

    def fake_dispatch(query: str, config: Configuration, loop_count: int):
        return {"results": []}, ["没有结果"], None, "duckduckgo"

    executor = TaskExecutor(
        config=make_config(),
        summarizer=FakeSummarizer(),
        state_lock=Lock(),
        drain_tool_events=lambda state, step=None: [],
        search_dispatcher=fake_dispatch,
        context_preparer=lambda search_result, answer_text, config: ("", ""),
    )

    events = list(executor.execute(state, task, emit_stream=True, step=2))

    assert task.status == "skipped"
    assert task.notices == ["没有结果"]
    assert events == [
        {"type": "status", "message": "没有结果", "task_id": 1, "step": 2},
        {
            "type": "task_status",
            "task_id": 1,
            "status": "skipped",
            "title": "任务一",
            "intent": "了解现状",
            "note_id": None,
            "note_path": None,
            "step": 2,
        },
    ]
    assert state.web_research_results == []
    assert state.sources_gathered == []
    assert state.research_loop_count == 0
