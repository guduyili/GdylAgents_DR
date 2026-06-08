"""流式运行服务：负责 SSE 事件编排、任务并发和最终报告事件。"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from queue import Queue
from threading import Thread
from typing import Any, Protocol

from models import SummaryState, TodoItem
from services.planner import PlanningService
from services.reporter import ReportingService
from services.research_run_store import ResearchRunStore
from services.stream_events import normalize_stream_event
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
        run_store: ResearchRunStore | None = None,
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
        self._run_store = run_store

    def run(self, topic: str, todo_items: list[TodoItem] | None = None) -> Iterator[dict[str, Any]]:
        """流式执行研究流程，通过 SSE 逐步推送进度事件。"""
        run_id = self._run_id_factory()
        state = SummaryState(research_topic=topic)
        state.run_id = run_id
        logger.debug("开始流式研究： run_id=%s topic=%s", run_id, topic)

        if self._run_store is not None:
            self._run_store.start_run(run_id=run_id, topic=topic)

        yield from self._run_flow(state, run_id, todo_items)

    def _run_flow(
        self,
        state: SummaryState,
        run_id: str,
        todo_items: list[TodoItem] | None,
    ) -> Iterator[dict[str, Any]]:
        """内部流程：生成事件、记录到 store、yield 到前端。"""
        yield self._emit({"type": "status", "message": "初始化研究流程"}, run_id=run_id)

        if todo_items is not None:
            state.todo_items = todo_items
        else:
            state.todo_items = self._planner.plan_todo_list(state)
            for event in self._drain_tool_events(state, step=0):
                yield self._emit(event, run_id=run_id)

        if not state.todo_items:
            state.todo_items = [self._planner.create_fallback_task(state=state)]

        for task in state.todo_items:
            task.task_run_id = f"{run_id}:task:{task.id}"

        channel_map = self._assign_stream_channels(state.todo_items)
        yield self._emit(
            {
                "type": "todo_list",
                "tasks": [self._serialize_task(t) for t in state.todo_items],
                "step": 0,
            },
            run_id=run_id,
        )

        yield from self._run_task_workers(state, channel_map, run_id=run_id)
        yield from self._emit_final_report(state, run_id=run_id)

        if self._run_store is not None:
            self._run_store.complete_run(run_id)

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
    ) -> Iterator[dict[str, Any]]:
        event_queue: Queue[dict[str, Any]] = Queue()

        def enqueue(
            event: dict[str, Any],
            *,
            task: TodoItem | None = None,
            step_override: int | None = None,
        ) -> None:
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

            event_queue.put(self._emit(payload, run_id=run_id))

        def tool_event_sink(event: dict[str, Any]) -> None:
            enqueue(event)

        self._set_tool_event_sink(tool_event_sink)
        threads: list[Thread] = []

        def worker(task: TodoItem, step: int) -> None:
            try:
                enqueue(
                    {
                        "type": "task_status",
                        "task_id": task.id,
                        "status": "in_progress",
                        "title": task.title,
                        "intent": task.intent,
                        "note_id": task.note_id,
                        "note_path": task.note_path,
                    },
                    task=task,
                )
                for event in self._task_executor.execute(state, task, emit_stream=True, step=step):
                    enqueue(event, task=task)
            except Exception as exc:
                logger.exception("任务执行失败: run_id=%s task_id=%s", run_id, task.id, exc_info=exc)
                enqueue(
                    {
                        "type": "task_status",
                        "task_id": task.id,
                        "status": "failed",
                        "error": str(exc),
                        "title": task.title,
                        "intent": task.intent,
                        "note_id": task.note_id,
                        "note_path": task.note_path,
                    },
                    task=task,
                )
            finally:
                enqueue({"type": "__task_done__", "task_id": task.id})

        for task in state.todo_items:
            step = channel_map.get(task.id, {}).get("step", 0)
            thread = Thread(target=worker, args=(task, step), daemon=True)
            threads.append(thread)
            thread.start()

        active_workers = len(state.todo_items)
        finished_workers = 0
        try:
            while finished_workers < active_workers:
                event = event_queue.get()
                if event.get("type") == "__task_done__":
                    finished_workers += 1
                    continue
                yield event
        finally:
            self._set_tool_event_sink(None)
            for thread in threads:
                thread.join()

    def _emit_final_report(self, state: SummaryState, *, run_id: str) -> Iterator[dict[str, Any]]:
        final_step = len(state.todo_items) + 1
        try:
            report = self._reporting.generate_report(state)
        except Exception as exc:
            logger.exception("报告生成失败，将使用任务摘要兜底: run_id=%s error=%s", run_id, exc)
            summaries = "\n\n".join(
                f"### {t.title}\n{t.summary or '暂无摘要'}"
                for t in state.todo_items
            )
            report = f"## 研究摘要（报告生成失败，使用任务摘要兜底）\n\n{summaries}"

        for event in self._drain_tool_events(state, step=final_step):
            yield self._emit(event, run_id=run_id)
        state.structured_report = report
        state.running_summary = report

        note_event = self._persist_final_report(state, report)
        if note_event:
            yield self._emit(note_event, run_id=run_id)

        yield self._emit(
            {
                "type": "final_report",
                "report": report,
                "note_id": state.report_note_id,
                "note_path": state.report_note_path,
            },
            run_id=run_id,
        )
        yield self._emit({"type": "done"}, run_id=run_id)

    def _emit(self, event: dict[str, Any], *, run_id: str) -> dict[str, Any]:
        """为公开 SSE 事件补充链路追踪字段，并记录到 run_store。"""
        payload = self._with_observability(event, run_id=run_id)
        if self._run_store is not None and payload.get("type") != "__task_done__":
            self._run_store.record_event(run_id, payload)
        return payload

    def _with_observability(self, event: dict[str, Any], *, run_id: str) -> dict[str, Any]:
        """为事件补充 run_id/timestamp 并按强类型 SSE 协议校验。"""
        return normalize_stream_event(event, run_id=run_id, timestamp=self._clock())