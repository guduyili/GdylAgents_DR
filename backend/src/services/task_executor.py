"""任务执行服务：负责单个研究任务的搜索、上下文整理和总结。"""

from __future__ import annotations

import time
import json
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Any, Protocol

from config import Configuration
from models import SummaryState, TodoItem
from services.browser_fetch import BrowserFetchService
from services.cancellation import ResearchCancelled, ScopedStopSignal, ensure_not_cancelled, is_cancelled
from services.fact_check_service import FactCheckService
from services.research_pipeline import ResearchPipelineConfig
from services.search import dispatch_search, prepare_research_context
from services.skill_loader import SkillLoader
from services.search_backends import CancellableSearchBackend, SearchBackend, SearchOutcome
from services.decision_loop import DecisionLoop, DecisionLoopError
from services.stream_events import build_stream_event
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
        search_backend: SearchBackend | None = None,
        browser_fetch_service: BrowserFetchService | None = None,
        fact_check_service: FactCheckService | None = None,
        skill_loader: SkillLoader | None = None,
        pipeline_config: ResearchPipelineConfig | None = None,
        context_preparer: ContextPreparer = prepare_research_context,
        monotonic_clock: Callable[[], float] | None = None,
        decision_provider: Callable | None = None,
    ) -> None:
        self._config = config
        self._summarizer = summarizer
        self._state_lock = state_lock
        self._drain_tool_events = drain_tool_events
        self._search_dispatcher = search_dispatcher
        self._search_backend = search_backend
        self._browser_fetch_service = browser_fetch_service or BrowserFetchService()
        self._fact_check_service = fact_check_service or FactCheckService()
        self._skill_loader = skill_loader or SkillLoader(config.skills_workspace)
        self._pipeline_config = pipeline_config or ResearchPipelineConfig.from_csv(
            config.research_pipeline
        )
        self._context_preparer = context_preparer
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._decision_provider = decision_provider
        self.last_search_notices: list[str] = []

    def execute(
        self,
        state: SummaryState,
        task: TodoItem,
        *,
        emit_stream: bool,
        step: int | None = None,
        stop_event: Event | None = None,
    ) -> Iterator[dict[str, Any]]:
        """执行单个任务，并在流式模式下产出 SSE 事件。"""
        task_started_at = self._monotonic_clock()
        task.status = "in_progress"

        if is_cancelled(stop_event):
            yield from self._cancel_task(
                task,
                emit_stream=emit_stream,
                step=step,
                task_started_at=task_started_at,
            )
            return

        try:
            if self._config.task_execution_mode == "decision":
                search_result, notices, answer_text, backend = yield from self._run_decision_search(
                    state, task, emit_stream=emit_stream, step=step, stop_event=stop_event,
                )
            else:
                search_result, notices, answer_text, backend = self._run_search_with_timeout(
                    task.query, state.research_loop_count, stop_event=stop_event,
                )
        except ResearchCancelled:
            yield from self._cancel_task(
                task,
                emit_stream=emit_stream,
                step=step,
                task_started_at=task_started_at,
            )
            return
        except (TimeoutError, DecisionLoopError) as exc:
            yield from self._fail_task(
                state,
                task,
                error=str(exc),
                emit_stream=emit_stream,
                step=step,
                task_started_at=task_started_at,
            )
            return

        if search_result:
            search_result, browser_notices = self._browser_fetch_service.enrich_search_payload(
                search_result,
                config=self._config,
            )
            if browser_notices:
                notices = list(notices) + browser_notices

        self.last_search_notices = notices
        task.notices = notices

        yield from self._drain_after_search(state, emit_stream=emit_stream, step=step)

        if notices and emit_stream:
            for notice in notices:
                if notice:
                    yield build_stream_event(
                        {
                            "type": "status",
                            "message": notice,
                            "task_id": task.id,
                            "step": step,
                            "source": "task_executor",
                        }
                    )

        if not search_result or not search_result.get("results"):
            task.status = "skipped"
            if emit_stream:
                yield from self._drain_tool_events(state, step=step)
                yield build_stream_event(
                    {
                        "type": "task_status",
                        "task_id": task.id,
                        "status": "skipped",
                        "title": task.title,
                        "intent": task.intent,
                        "note_id": task.note_id,
                        "note_path": task.note_path,
                        "step": step,
                        "source": "task_executor",
                        "duration_ms": self._elapsed_ms(task_started_at),
                    }
                )
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
        context, skill_events = self._apply_skills(task, context)
        if emit_stream:
            yield from skill_events

        with self._state_lock:
            state.web_research_results.append(context)
            state.sources_gathered.append(sources_summary)
            state.research_loop_count += 1

        if emit_stream:
            yield from self._run_streaming_summary(
                state,
                task,
                context,
                backend,
                step,
                task_started_at,
                stop_event=stop_event,
            )
        else:
            try:
                summary_text = self._run_summary_with_timeout(state, task, context)
            except TimeoutError as exc:
                self._fail_task(
                    state,
                    task,
                    error=str(exc),
                    emit_stream=False,
                    step=step,
                    task_started_at=task_started_at,
                )
                return
            self._drain_tool_events(state, step=None)
            self._complete_task(task, summary_text)
            self._drain_tool_events(state, step=None)

    def _apply_skills(
        self,
        task: TodoItem,
        context: str,
    ) -> tuple[str, Iterator[dict[str, Any]]]:
        if not self._pipeline_config.is_enabled("summarize"):
            return context, iter(())

        addon, loaded = self._skill_loader.build_context_addon(
            title=task.title,
            intent=task.intent,
            query=task.query,
        )
        if not addon:
            return context, iter(())

        merged_context = f"{context}\n\n{addon}".strip()

        def skill_events() -> Iterator[dict[str, Any]]:
            for skill in loaded:
                yield build_stream_event(
                    {
                        "type": "skill_loaded",
                        "task_id": task.id,
                        "skill_name": skill.name,
                        "skill_description": skill.description,
                        "preview": skill.preview,
                        "source": "skill_loader",
                    }
                )

        return merged_context, skill_events()

    def _emit_fact_check(
        self,
        task: TodoItem,
        *,
        emit_stream: bool,
        step: int | None,
    ) -> Iterator[dict[str, Any]]:
        if not self._config.enable_fact_check or not self._pipeline_config.is_enabled("fact_check"):
            return
        if task.status != "completed":
            return

        result = self._fact_check_service.check(task)
        if not emit_stream:
            return

        yield build_stream_event(
            {
                "type": "fact_check_result",
                "task_id": task.id,
                "passed": result.passed,
                "score": result.score,
                "matched_sources": result.matched_sources,
                "warnings": result.warnings,
                "missing_terms": result.missing_terms,
                "step": step,
                "source": "fact_check_service",
            }
        )

    def _cancel_task(
        self,
        task: TodoItem,
        *,
        emit_stream: bool,
        step: int | None,
        task_started_at: float,
    ) -> Iterator[dict[str, Any]]:
        task.status = "cancelled"
        if not emit_stream:
            return
        yield build_stream_event(
            {
                "type": "task_status",
                "task_id": task.id,
                "status": "cancelled",
                "error": "任务已取消",
                "title": task.title,
                "intent": task.intent,
                "note_id": task.note_id,
                "note_path": task.note_path,
                "step": step,
                "source": "task_executor",
                "duration_ms": self._elapsed_ms(task_started_at),
            }
        )

    def _run_decision_search(self, state, task, *, emit_stream, step, stop_event):
        if self._decision_provider is None:
            raise DecisionLoopError("决策模式未配置决策器")
        task.decision_trace = []
        task.decision_stop_reason = None

        def decide(context, remaining):
            budget = min(remaining, self._config.decision_timeout_seconds)
            return self._call_with_timeout(
                lambda: self._decision_provider(context, budget),
                timeout_seconds=budget, operation="决策", stop_event=stop_event,
            )

        def search(query, remaining):
            payload, notices, answer, backend = self._run_search_with_timeout(
                query, state.research_loop_count, stop_event=stop_event, timeout_seconds=remaining,
            )
            return SearchOutcome(payload or {"results": []}, notices, answer, backend)

        loop = DecisionLoop(
            max_steps=self._config.decision_max_steps,
            timeout_seconds=self._config.decision_total_timeout_seconds,
            clock=self._monotonic_clock,
        ).run(task, state.research_topic, decide=decide, search=search, stop_event=stop_event)
        while True:
            try:
                record = next(loop)
            except StopIteration as done:
                result = done.value
                break
            except ResearchCancelled:
                task.decision_stop_reason = "cancelled"
                raise
            task.decision_trace.append(record)
            if record["action"] == "stop":
                task.decision_stop_reason = record["stop_reason"]
            if emit_stream:
                yield build_stream_event({
                    "type": "status", "task_id": task.id, "step": step,
                    "source": "decision_loop",
                    "message": "任务决策 " + json.dumps(record, ensure_ascii=False),
                })
        outcome = result.outcome
        if not outcome.payload["results"] and result.stop_reason in {
            "timeout", "invalid_action", "decision_error",
        }:
            raise DecisionLoopError(f"决策循环未获得证据：{result.stop_reason}")
        return outcome.payload, outcome.notices, outcome.answer_text, outcome.backend_label

    def _run_search_with_timeout(
        self,
        query: str,
        loop_count: int,
        *,
        stop_event: Event | None = None,
        timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], str | None, str]:
        search_stop = ScopedStopSignal(stop_event)
        budget = self._config.search_timeout_seconds
        if timeout_seconds is not None:
            budget = min(budget, timeout_seconds)

        def run_search() -> tuple[dict[str, Any] | None, list[str], str | None, str]:
            ensure_not_cancelled(search_stop)
            if self._search_backend is not None:
                if isinstance(self._search_backend, CancellableSearchBackend):
                    outcome = self._search_backend.search_with_cancellation(
                        query, config=self._config, loop_count=loop_count,
                        stop_event=search_stop,
                        timeout_seconds=budget,
                    )
                else:
                    outcome = self._search_backend.search(
                        query, config=self._config, loop_count=loop_count,
                    )
                ensure_not_cancelled(search_stop)
                return outcome.payload, outcome.notices, outcome.answer_text, outcome.backend_label

            if self._search_dispatcher is dispatch_search:
                result = dispatch_search(
                    query, self._config, loop_count, stop_event=search_stop,
                    timeout_seconds=budget,
                )
            else:
                result = self._search_dispatcher(query, self._config, loop_count)
            ensure_not_cancelled(search_stop)
            return result

        try:
            return self._call_with_timeout(
                run_search,
                timeout_seconds=budget,
                operation="搜索",
                stop_event=stop_event,
            )
        finally:
            # The caller may have timed out while the SDK is still running.
            # Stop later attempts without cancelling sibling tasks or the run.
            search_stop.set()

    def _run_summary_with_timeout(
        self,
        state: SummaryState,
        task: TodoItem,
        context: str,
    ) -> str:
        return self._call_with_timeout(
            lambda: self._summarizer.summarize_task(state, task, context),
            timeout_seconds=self._config.summary_timeout_seconds,
            operation="总结",
        )

    def _call_with_timeout(
        self,
        fn: Callable[[], Any],
        *,
        timeout_seconds: float,
        operation: str,
        stop_event: Event | None = None,
    ) -> Any:
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(fn)
            deadline = self._monotonic_clock() + timeout_seconds
            while True:
                ensure_not_cancelled(stop_event)
                remaining = deadline - self._monotonic_clock()
                if remaining <= 0:
                    raise TimeoutError(f"{operation}超时（{timeout_seconds}s）")
                try:
                    return future.result(timeout=min(0.2, remaining))
                except FuturesTimeoutError:
                    continue
        finally:
            # Release the caller on timeout/cancel; running tools must finish themselves.
            executor.shutdown(wait=False, cancel_futures=True)

    def _fail_task(
        self,
        state: SummaryState,
        task: TodoItem,
        *,
        error: str,
        emit_stream: bool,
        step: int | None,
        task_started_at: float,
    ) -> Iterator[dict[str, Any]]:
        task.status = "failed"
        if emit_stream:
            yield from self._drain_tool_events(state, step=step)
            yield build_stream_event(
                {
                    "type": "task_status",
                    "task_id": task.id,
                    "status": "failed",
                    "error": error,
                    "title": task.title,
                    "intent": task.intent,
                    "note_id": task.note_id,
                    "note_path": task.note_path,
                    "step": step,
                    "source": "task_executor",
                    "duration_ms": self._elapsed_ms(task_started_at),
                }
            )

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
        task_started_at: float,
        *,
        stop_event: Event | None = None,
    ) -> Iterator[dict[str, Any]]:
        yield from self._drain_tool_events(state, step=step)
        yield build_stream_event(
            {
                "type": "sources",
                "task_id": task.id,
                "latest_sources": task.sources_summary,
                "raw_context": context,
                "step": step,
                "backend": backend,
                "note_id": task.note_id,
                "note_path": task.note_path,
                "source": "task_executor",
                "duration_ms": self._elapsed_ms(task_started_at),
            }
        )

        summary_started_at = self._monotonic_clock()
        summary_stream, summary_getter = self._summarizer.stream_task_summary(state, task, context)
        try:
            yield from self._drain_tool_events(state, step=step)
            for chunk in self._iter_summary_stream_with_timeout(summary_stream, stop_event=stop_event):
                if chunk:
                    yield build_stream_event(
                        {
                            "type": "task_summary_chunk",
                            "task_id": task.id,
                            "content": chunk,
                            "note_id": task.note_id,
                            "step": step,
                            "source": "summarizer",
                            "duration_ms": self._elapsed_ms(summary_started_at),
                        }
                    )
                yield from self._drain_tool_events(state, step=step)
        except ResearchCancelled:
            yield from self._cancel_task(
                task,
                emit_stream=True,
                step=step,
                task_started_at=task_started_at,
            )
            return
        except TimeoutError as exc:
            yield from self._fail_task(
                state,
                task,
                error=str(exc),
                emit_stream=True,
                step=step,
                task_started_at=task_started_at,
            )
            return

        if is_cancelled(stop_event):
            yield from self._cancel_task(
                task,
                emit_stream=True,
                step=step,
                task_started_at=task_started_at,
            )
            return

        summary_text = summary_getter()

        self._complete_task(task, summary_text)
        yield from self._drain_tool_events(state, step=step)
        yield from self._emit_fact_check(task, emit_stream=True, step=step)
        yield build_stream_event(
            {
                "type": "task_status",
                "task_id": task.id,
                "status": "completed",
                "summary": task.summary,
                "sources_summary": task.sources_summary,
                "note_id": task.note_id,
                "note_path": task.note_path,
                "step": step,
                "source": "task_executor",
                "duration_ms": self._elapsed_ms(task_started_at),
            }
        )

    def _iter_summary_stream_with_timeout(
        self,
        summary_stream: Iterator[str],
        *,
        stop_event: Event | None = None,
    ) -> Iterator[str]:
        chunk_queue: Queue[str | None] = Queue()
        producer_error: list[BaseException] = []

        def producer() -> None:
            try:
                for chunk in summary_stream:
                    chunk_queue.put(chunk)
            except BaseException as exc:  # noqa: BLE001 - propagate producer failures
                producer_error.append(exc)
            finally:
                chunk_queue.put(None)

        thread = Thread(target=producer, daemon=True)
        thread.start()

        deadline = self._monotonic_clock() + self._config.summary_timeout_seconds
        while True:
            ensure_not_cancelled(stop_event)
            remaining = deadline - self._monotonic_clock()
            if remaining <= 0:
                raise TimeoutError(f"总结超时（{self._config.summary_timeout_seconds}s）")

            try:
                chunk = chunk_queue.get(timeout=min(0.2, remaining))
            except Empty:
                continue

            if producer_error:
                raise producer_error[0]

            if chunk is None:
                break

            yield chunk

    @staticmethod
    def _complete_task(task: TodoItem, summary_text: str | None) -> None:
        task.summary = summary_text.strip() if summary_text else "暂无可用信息"
        task.status = "completed"

    def _elapsed_ms(self, started_at: float) -> int:
        """返回从 started_at 到当前单调时钟的非负毫秒数。"""
        return max(0, int((self._monotonic_clock() - started_at) * 1000))
