"""流式运行服务：负责 SSE 事件编排、任务并发和最终报告事件。"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from queue import Empty, Queue
from threading import Event
from typing import Any, Protocol

from models import SummaryState, TodoItem
from services.cancellation import is_cancelled
from services.planner import PlanningService
from services.reporter import ReportingService
from services.research_run_store import ResearchRunStore
from services.report_post_processor import ReportPostProcessor
from services.research_pipeline import ResearchPipelineConfig
from services.review_service import ReviewService
from services.stream_events import build_stream_event, normalize_stream_event
from services.task_executor import TaskExecutor

logger = logging.getLogger(__name__)


class DrainToolEvents(Protocol):
    def __call__(
        self,
        state: SummaryState,
        *,
        step: int | None = None,
    ) -> list[dict[str, Any]]: ...


class SetToolEventSink(Protocol):
    def __call__(self, sink: Callable[[dict[str, Any]], None] | None) -> None: ...


class PersistFinalReport(Protocol):
    def __call__(self, state: SummaryState, report: str) -> dict[str, Any] | None: ...


class SerializeTask(Protocol):
    def __call__(self, task: TodoItem) -> dict[str, Any]: ...


class StreamRunner:
    """运行流式研究流程，并产出前端 SSE 事件字典。"""

    def __init__(
        self,
        *,
        planner: PlanningService,
        task_executor: TaskExecutor,
        reporting: ReportingService,
        drain_tool_events: DrainToolEvents,
        set_tool_event_sink: SetToolEventSink,
        persist_final_report: PersistFinalReport,
        serialize_task: SerializeTask,
        run_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], str] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
        run_store: ResearchRunStore | None = None,
        max_concurrent_tasks: int = 4,
        research_mode: str = "deep",
        review_service: ReviewService | None = None,
        enable_report_review: bool = True,
        pipeline_config: ResearchPipelineConfig | None = None,
        report_post_processor: ReportPostProcessor | None = None,
    ) -> None:
        self._planner = planner
        self._task_executor = task_executor
        self._reporting = reporting
        self._drain_tool_events = drain_tool_events
        self._set_tool_event_sink = set_tool_event_sink
        self._persist_final_report = persist_final_report
        self._serialize_task = serialize_task
        self._run_id_factory = run_id_factory or (lambda: uuid.uuid4().hex)
        self._clock = clock or (lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._run_store = run_store
        self._max_concurrent_tasks = max(1, max_concurrent_tasks)
        self._research_mode = research_mode
        self._review_service = review_service
        self._enable_report_review = enable_report_review
        self._pipeline_config = pipeline_config or ResearchPipelineConfig()
        self._report_post_processor = report_post_processor or ReportPostProcessor()

    def run(
        self,
        topic: str,
        todo_items: list[TodoItem] | None = None,
        *,
        stop_event: Event | None = None,
        run_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """流式执行研究流程，通过 SSE 逐步推送进度事件。"""
        run_id = run_id or self._run_id_factory()
        state = SummaryState(research_topic=topic)
        state.run_id = run_id
        setattr(state, "started_at", self._monotonic_clock())
        logger.debug("开始流式研究： run_id=%s topic=%s", run_id, topic)

        if self._run_store is not None:
            self._run_store.start_run(run_id=run_id, topic=topic)

        yield from self._run_flow(state, run_id, todo_items, stop_event=stop_event)

    def _run_flow(
        self,
        state: SummaryState,
        run_id: str,
        todo_items: list[TodoItem] | None,
        *,
        stop_event: Event | None = None,
    ) -> Iterator[dict[str, Any]]:
        """内部流程：生成事件、记录到 store、yield 到前端。"""
        phase_durations: dict[str, int] = {}
        planning_started_at = self._monotonic_clock()

        yield self._emit(
            build_stream_event(
                {"type": "status", "message": "初始化研究流程", "source": "stream_runner"}
            ),
            run_id=run_id,
        )

        if is_cancelled(stop_event):
            yield from self._emit_cancelled(state, run_id=run_id, phase_durations=phase_durations)
            return

        if todo_items is not None:
            state.todo_items = todo_items
        elif self._research_mode == "quick":
            state.todo_items = [self._build_quick_task(state)]
        else:
            state.todo_items = self._planner.plan_todo_list(state)
            for event in self._drain_tool_events(state, step=0):
                event.setdefault("source", "tool")
                yield self._emit(event, run_id=run_id)

        if is_cancelled(stop_event):
            yield from self._emit_cancelled(state, run_id=run_id, phase_durations=phase_durations)
            return

        if not state.todo_items:
            state.todo_items = [self._planner.create_fallback_task(state=state)]

        for task in state.todo_items:
            task.task_run_id = f"{run_id}:task:{task.id}"

        channel_map = self._assign_stream_channels(state.todo_items)
        yield self._emit(
            build_stream_event(
                {
                    "type": "todo_list",
                    "tasks": [self._serialize_task(t) for t in state.todo_items],
                    "step": 0,
                    "source": "stream_runner",
                }
            ),
            run_id=run_id,
        )

        phase_durations["planning"] = self._elapsed_ms(planning_started_at)
        yield from self._emit_phase_duration("planning", phase_durations["planning"], run_id=run_id)

        yield from self._run_task_workers(
            state,
            channel_map,
            run_id=run_id,
            phase_durations=phase_durations,
            stop_event=stop_event,
        )

        if is_cancelled(stop_event):
            yield from self._emit_cancelled(state, run_id=run_id, phase_durations=phase_durations)
            return

        yield from self._emit_final_report(state, run_id=run_id, phase_durations=phase_durations)

        if self._run_store is not None:
            self._run_store.complete_run(run_id, phase_durations=phase_durations)

    def _build_quick_task(self, state: SummaryState) -> TodoItem:
        topic = state.research_topic.strip()
        title = f"快速浏览：{topic[:40]}" if len(topic) > 40 else f"快速浏览：{topic}"
        return TodoItem(
            id=1,
            title=title,
            intent="快速获取主题概览与要点摘要",
            query=topic,
        )

    def _build_quick_report(self, state: SummaryState) -> str:
        lines = [f"# {state.research_topic}", ""]
        for task in state.todo_items:
            lines.append(f"## {task.title}")
            lines.append(task.summary or "暂无摘要")
            if task.sources_summary:
                lines.extend(["", "### 来源", task.sources_summary])
        return "\n\n".join(lines).strip()

    def _assign_stream_channels(self, tasks: list[TodoItem]) -> dict[int, dict[str, Any]]:
        channel_map: dict[int, dict[str, Any]] = {}
        for index, task in enumerate(tasks, start=1):
            token = f"task_{task.id}"
            task.stream_token = token
            channel_map[task.id] = {"step": index, "token": token}
        return channel_map

    def _run_task_workers(
        self,
        state: SummaryState,
        channel_map: dict[int, dict[str, Any]],
        *,
        run_id: str,
        phase_durations: dict[str, int],
        stop_event: Event | None = None,
    ) -> Iterator[dict[str, Any]]:
        event_queue: Queue[dict[str, Any]] = Queue()
        task_start_times: dict[int, float] = {}
        task_sources_ms: dict[int, int] = {}
        phase_search_ms = 0
        phase_summary_ms = 0

        def enqueue(
            event: dict[str, Any],
            *,
            task: TodoItem | None = None,
            step_override: int | None = None,
        ) -> None:
            nonlocal phase_search_ms, phase_summary_ms
            payload = dict(event)
            target_task_id = payload.get("task_id")
            if task is not None:
                target_task_id = task.id
                payload["task_id"] = task.id
                if task.task_run_id:
                    payload["task_run_id"] = task.task_run_id

            channel = channel_map.get(target_task_id) if target_task_id is not None else None
            if channel:
                payload.setdefault("step", channel["step"])
                payload["stream_token"] = channel["token"]
            if step_override is not None:
                payload["step"] = step_override

            event_type = payload.get("type")
            if event_type in {"sources", "task_status"}:
                payload.setdefault("source", "task_executor")
            elif event_type == "task_summary_chunk":
                payload.setdefault("source", "summarizer")
            elif event_type == "tool_call":
                payload.setdefault("source", "tool")

            if target_task_id is not None and event_type in {"sources", "task_status"}:
                started_at = task_start_times.get(int(target_task_id))
                if started_at is not None:
                    payload.setdefault("duration_ms", self._elapsed_ms(started_at))

            emitted = self._emit(payload, run_id=run_id)
            if event_type == "sources" and target_task_id is not None:
                task_sources_ms[int(target_task_id)] = int(emitted.get("duration_ms") or 0)
            elif event_type == "task_status" and target_task_id is not None:
                status = emitted.get("status")
                if status in {"completed", "failed", "skipped"}:
                    total_ms = int(emitted.get("duration_ms") or 0)
                    search_ms = task_sources_ms.get(int(target_task_id), 0)
                    phase_search_ms += search_ms
                    phase_summary_ms += max(0, total_ms - search_ms)
            event_queue.put(emitted)

        def tool_event_sink(event: dict[str, Any]) -> None:
            enqueue(event)

        self._set_tool_event_sink(tool_event_sink)

        def worker(task: TodoItem, step: int) -> None:
            if is_cancelled(stop_event):
                enqueue({"type": "__task_done__", "task_id": task.id})
                return

            task_start_times[task.id] = self._monotonic_clock()
            try:
                enqueue(
                    build_stream_event(
                        {
                            "type": "task_status",
                            "task_id": task.id,
                            "status": "in_progress",
                            "title": task.title,
                            "intent": task.intent,
                            "note_id": task.note_id,
                            "note_path": task.note_path,
                            "source": "task_executor",
                            "duration_ms": 0,
                        }
                    ),
                    task=task,
                )
                for event in self._task_executor.execute(
                    state,
                    task,
                    emit_stream=True,
                    step=step,
                    stop_event=stop_event,
                ):
                    enqueue(event, task=task)
            except Exception as exc:
                logger.exception("任务执行失败: run_id=%s task_id=%s", run_id, task.id)
                enqueue(
                    build_stream_event(
                        {
                            "type": "task_status",
                            "task_id": task.id,
                            "status": "failed",
                            "error": str(exc),
                            "title": task.title,
                            "intent": task.intent,
                            "note_id": task.note_id,
                            "note_path": task.note_path,
                            "source": "task_executor",
                        }
                    ),
                    task=task,
                )
            finally:
                enqueue({"type": "__task_done__", "task_id": task.id})

        active_workers = len(state.todo_items)
        finished_workers = 0
        executor = ThreadPoolExecutor(max_workers=self._max_concurrent_tasks)
        try:
            for task in state.todo_items:
                step = channel_map.get(task.id, {}).get("step", 0)
                executor.submit(worker, task, step)

            try:
                while finished_workers < active_workers:
                    if is_cancelled(stop_event):
                        break

                    try:
                        event = event_queue.get(timeout=0.2)
                    except Empty:
                        continue

                    if event.get("type") == "__task_done__":
                        finished_workers += 1
                        yield from self._drain_public_events(
                            event_queue,
                            pending=event_queue.qsize(),
                        )
                        continue
                    yield event
            finally:
                self._set_tool_event_sink(None)
                yield from self._drain_public_events(event_queue)
        finally:
            executor.shutdown(wait=not is_cancelled(stop_event), cancel_futures=is_cancelled(stop_event))

        phase_durations["search"] = phase_search_ms
        phase_durations["summary"] = phase_summary_ms
        yield from self._emit_phase_duration("search", phase_search_ms, run_id=run_id)
        yield from self._emit_phase_duration("summary", phase_summary_ms, run_id=run_id)

    def _emit_final_report(
        self,
        state: SummaryState,
        *,
        run_id: str,
        phase_durations: dict[str, int],
    ) -> Iterator[dict[str, Any]]:
        final_step = len(state.todo_items) + 1
        report_started_at = self._monotonic_clock()
        try:
            if self._research_mode == "quick":
                report = self._build_quick_report(state)
            else:
                report = self._reporting.generate_report(state)
        except Exception as exc:
            logger.exception("报告生成失败，将使用任务摘要兜底: run_id=%s error=%s", run_id, exc)
            summaries = "\n\n".join(
                f"### {t.title}\n{t.summary or '暂无摘要'}"
                for t in state.todo_items
            )
            report = f"## 研究摘要（报告生成失败，使用任务摘要兜底）\n\n{summaries}"

        if self._pipeline_config.is_enabled("report"):
            processed = self._report_post_processor.process(
                report,
                sources_gathered=state.sources_gathered,
            )
            report = processed.report

        for event in self._drain_tool_events(state, step=final_step):
            event.setdefault("source", "tool")
            yield self._emit(event, run_id=run_id)
        state.structured_report = report
        state.running_summary = report

        note_event = self._persist_final_report(state, report)
        if note_event:
            note_event.setdefault("source", "report_persistence")
            note_event.setdefault("duration_ms", self._elapsed_ms(report_started_at))
            yield self._emit(note_event, run_id=run_id)

        yield self._emit(
            build_stream_event(
                {
                    "type": "final_report",
                    "report": report,
                    "note_id": state.report_note_id,
                    "note_path": state.report_note_path,
                    "source": "reporter" if self._research_mode != "quick" else "stream_runner",
                    "duration_ms": self._elapsed_ms(report_started_at),
                }
            ),
            run_id=run_id,
        )

        if (
            self._enable_report_review
            and self._pipeline_config.is_enabled("review")
            and self._review_service is not None
        ):
            review = self._review_service.review(state, report)
            yield self._emit(
                build_stream_event(
                    {
                        "type": "review_result",
                        "passed": review.passed,
                        "score": review.score,
                        "issues": review.issues,
                        "suggestions": review.suggestions,
                        "source": "review_service",
                    }
                ),
                run_id=run_id,
            )

        report_duration_ms = self._elapsed_ms(report_started_at)
        phase_durations["report"] = report_duration_ms
        yield from self._emit_phase_duration("report", report_duration_ms, run_id=run_id)

        run_started_at = getattr(state, "started_at", report_started_at)
        total_duration_ms = self._elapsed_ms(run_started_at)
        phase_durations["total"] = total_duration_ms
        yield from self._emit_phase_duration("total", total_duration_ms, run_id=run_id)

        yield self._emit(
            build_stream_event(
                {
                    "type": "done",
                    "source": "stream_runner",
                    "duration_ms": total_duration_ms,
                }
            ),
            run_id=run_id,
        )

    def _drain_public_events(
        self,
        event_queue: Queue[dict[str, Any]],
        *,
        pending: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Drain queued public events that arrived around worker completion."""
        remaining = pending if pending is not None else event_queue.qsize()
        for _ in range(remaining):
            if event_queue.empty():
                break
            event = event_queue.get_nowait()
            if event.get("type") == "__task_done__":
                continue
            yield event

    def _emit_cancelled(
        self,
        state: SummaryState,
        *,
        run_id: str,
        phase_durations: dict[str, int],
    ) -> Iterator[dict[str, Any]]:
        run_started_at = getattr(state, "started_at", self._monotonic_clock())
        total_duration_ms = self._elapsed_ms(run_started_at)
        phase_durations["total"] = total_duration_ms

        yield self._emit(
            build_stream_event(
                {
                    "type": "status",
                    "message": "研究已取消",
                    "source": "stream_runner",
                }
            ),
            run_id=run_id,
        )
        yield self._emit(
            build_stream_event(
                {
                    "type": "cancelled",
                    "message": "研究已取消",
                    "source": "stream_runner",
                    "duration_ms": total_duration_ms,
                }
            ),
            run_id=run_id,
        )

        if self._run_store is not None:
            self._run_store.cancel_run(run_id, phase_durations=phase_durations)

    def _emit_phase_duration(
        self,
        phase: str,
        duration_ms: int,
        *,
        run_id: str,
    ) -> Iterator[dict[str, Any]]:
        yield self._emit(
            build_stream_event(
                {
                    "type": "phase_duration",
                    "phase": phase,
                    "duration_ms": duration_ms,
                    "source": "stream_runner",
                }
            ),
            run_id=run_id,
        )

    def _emit(self, event: dict[str, Any], *, run_id: str) -> dict[str, Any]:
        """为公开 SSE 事件补充链路追踪字段，并记录到 run_store。"""
        payload = self._with_observability(event, run_id=run_id)
        if self._run_store is not None and payload.get("type") != "__task_done__":
            self._run_store.record_event(run_id, payload)
        return payload

    def _with_observability(self, event: dict[str, Any], *, run_id: str) -> dict[str, Any]:
        """为事件补充 run_id/timestamp 并按强类型 SSE 协议校验。"""
        return normalize_stream_event(event, run_id=run_id, timestamp=self._clock())

    def _elapsed_ms(self, started_at: float) -> int:
        """返回从 started_at 到当前单调时钟的非负毫秒数。"""
        return max(0, int((self._monotonic_clock() - started_at) * 1000))
