"""任务执行服务：负责单个研究任务的搜索、上下文整理和总结。"""

from __future__ import annotations

from collections.abc import Iterator
from threading import Lock
from typing import Any, Protocol

from config import Configuration
from models import SummaryState, TodoItem
from services.search import dispatch_search, prepare_research_context
from services.summarizer import SummarizationService


class DrainToolEvents(Protocol):
    def __call__(
        self,
        state: SummaryState,
        *,
        step: int | None = None,
    ) -> list[dict[str, Any]]: ...


class SearchDispatcher(Protocol):
    def __call__(
        self,
        query: str,
        config: Configuration,
        loop_count: int,
    ) -> tuple[dict[str, Any] | None, list[str], str | None, str]: ...


class ContextPreparer(Protocol):
    def __call__(
        self,
        search_result: dict[str, Any] | None,
        answer_text: str | None,
        config: Configuration,
    ) -> tuple[str, str]: ...


class TaskExecutor:
    """执行单个任务：搜索 → 准备上下文 → 总结。"""

    def __init__(
        self,
        *,
        config: Configuration,
        summarizer: SummarizationService,
        state_lock: Lock,
        drain_tool_events: DrainToolEvents,
        search_dispatcher: SearchDispatcher = dispatch_search,
        context_preparer: ContextPreparer = prepare_research_context,
    ) -> None:
        self._config = config
        self._summarizer = summarizer
        self._state_lock = state_lock
        self._drain_tool_events = drain_tool_events
        self._search_dispatcher = search_dispatcher
        self._context_preparer = context_preparer
        self.last_search_notices: list[str] = []

    def execute(
        self,
        state: SummaryState,
        task: TodoItem,
        *,
        emit_stream: bool,
        step: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """执行单个任务，并在流式模式下产出 SSE 事件。"""
        task.status = "in_progress"

        search_result, notices, answer_text, backend = self._search_dispatcher(
            task.query,
            self._config,
            state.research_loop_count,
        )
        self.last_search_notices = notices
        task.notices = notices

        yield from self._drain_after_search(state, emit_stream=emit_stream, step=step)

        if notices and emit_stream:
            for notice in notices:
                if notice:
                    yield {
                        "type": "status",
                        "message": notice,
                        "task_id": task.id,
                        "step": step,
                    }

        if not search_result or not search_result.get("results"):
            task.status = "skipped"
            if emit_stream:
                yield from self._drain_tool_events(state, step=step)
                yield {
                    "type": "task_status",
                    "task_id": task.id,
                    "status": "skipped",
                    "title": task.title,
                    "intent": task.intent,
                    "note_id": task.note_id,
                    "note_path": task.note_path,
                    "step": step,
                }
            else:
                self._drain_tool_events(state, step=None)
            return

        if not emit_stream:
            self._drain_tool_events(state, step=None)

        sources_summary, context = self._context_preparer(
            search_result,
            answer_text,
            self._config,
        )
        task.sources_summary = sources_summary

        with self._state_lock:
            state.web_research_results.append(context)
            state.sources_gathered.append(sources_summary)
            state.research_loop_count += 1

        if emit_stream:
            yield from self._run_streaming_summary(state, task, context, backend, step)
        else:
            summary_text = self._summarizer.summarize_task(state, task, context)
            self._drain_tool_events(state, step=None)
            self._complete_task(task, summary_text)
            self._drain_tool_events(state, step=None)

    def _drain_after_search(
        self,
        state: SummaryState,
        *,
        emit_stream: bool,
        step: int | None,
    ) -> Iterator[dict[str, Any]]:
        if emit_stream:
            yield from self._drain_tool_events(state, step=step)
        else:
            self._drain_tool_events(state, step=None)

    def _run_streaming_summary(
        self,
        state: SummaryState,
        task: TodoItem,
        context: str,
        backend: str,
        step: int | None,
    ) -> Iterator[dict[str, Any]]:
        yield from self._drain_tool_events(state, step=step)
        yield {
            "type": "sources",
            "task_id": task.id,
            "latest_sources": task.sources_summary,
            "raw_context": context,
            "step": step,
            "backend": backend,
            "note_id": task.note_id,
            "note_path": task.note_path,
        }

        summary_stream, summary_getter = self._summarizer.stream_task_summary(state, task, context)
        try:
            yield from self._drain_tool_events(state, step=step)
            for chunk in summary_stream:
                if chunk:
                    yield {
                        "type": "task_summary_chunk",
                        "task_id": task.id,
                        "content": chunk,
                        "note_id": task.note_id,
                        "step": step,
                    }
                yield from self._drain_tool_events(state, step=step)
        finally:
            summary_text = summary_getter()

        self._complete_task(task, summary_text)
        yield from self._drain_tool_events(state, step=step)
        yield {
            "type": "task_status",
            "task_id": task.id,
            "status": "completed",
            "summary": task.summary,
            "sources_summary": task.sources_summary,
            "note_id": task.note_id,
            "note_path": task.note_path,
            "step": step,
        }

    @staticmethod
    def _complete_task(task: TodoItem, summary_text: str | None) -> None:
        task.summary = summary_text.strip() if summary_text else "暂无可用信息"
        task.status = "completed"
