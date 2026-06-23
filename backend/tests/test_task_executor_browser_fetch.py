from __future__ import annotations

from threading import Lock

from config import Configuration, SearchAPI
from models import SummaryState, TodoItem
from services.browser_fetch import BrowserFetchService, PageFetchResult
from services.task_executor import TaskExecutor


class FakeSummarizer:
    def summarize_task(self, state: SummaryState, task: TodoItem, context: str) -> str:
        return "摘要"


def make_task() -> TodoItem:
    return TodoItem(id=1, title="任务一", intent="了解现状", query="agent research")


def test_task_executor_applies_browser_fetch_notices_before_context_preparation() -> None:
    state = SummaryState(research_topic="AI Agent")
    task = make_task()
    captured: dict[str, object] = {}

    def fake_dispatch(query: str, config: Configuration, loop_count: int):
        return (
            {"results": [{"title": "A", "url": "https://example.com", "content": "短"}]},
            ["搜索提示"],
            None,
            "duckduckgo",
        )

    def fake_prepare(search_result, answer_text, config):
        captured["search_result"] = search_result
        return "来源摘要", "完整上下文"

    service = BrowserFetchService(
        http_fetcher=lambda url, **kwargs: PageFetchResult(
            url=url,
            content="补全页面正文" * 30,
            backend="http",
        )
    )

    executor = TaskExecutor(
        config=Configuration(
            search_api=SearchAPI.DUCKDUCKGO,
            enable_notes=False,
            fetch_full_page=True,
            enable_browser_fetch=True,
        ),
        summarizer=FakeSummarizer(),
        state_lock=Lock(),
        drain_tool_events=lambda state, step=None: [],
        search_dispatcher=fake_dispatch,
        browser_fetch_service=service,
        context_preparer=fake_prepare,
    )

    list(executor.execute(state, task, emit_stream=False))

    search_result = captured["search_result"]
    assert isinstance(search_result, dict)
    assert search_result["results"][0]["fetch_backend"] == "http"
    assert "http" in task.notices[-1]