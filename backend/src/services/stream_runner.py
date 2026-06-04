"""流式运行服务：负责 SSE 事件编排、任务并发和最终报告事件。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from queue import Queue
from threading import Thread
from typing import Any, Protocol

from models import SummaryState, TodoItem
from services.planner import PlanningService
from services.reporter import ReportingService
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
    ) -> None:
        self._planner = planner
        self._task_executor = task_executor
        self._reporting = reporting
        self._drain_tool_events = drain_tool_events
        self._set_tool_event_sink = set_tool_event_sink
        self._persist_final_report = persist_final_report
        self._serialize_task = serialize_task

    def run(self, topic: str, todo_items: list[TodoItem] | None = None) -> Iterator[dict[str, Any]]:
        """流式执行研究流程，通过 SSE 逐步推送进度事件。"""
        state = SummaryState(research_topic=topic)
        logger.debug("开始流式研究： topic=%s", topic)
        yield {"type": "status", "message": "初始化研究流程"}

        if todo_items is not None:
            state.todo_items = todo_items
        else:
            state.todo_items = self._planner.plan_todo_list(state)
            yield from self._drain_tool_events(state, step=0)

        if not state.todo_items:
            state.todo_items = [self._planner.create_fallback_task(state=state)]

        channel_map = self._assign_stream_channels(state.todo_items)
        yield {
            "type": "todo_list",
            "tasks": [self._serialize_task(t) for t in state.todo_items],
            "step": 0,
        }

        yield from self._run_task_workers(state, channel_map)
        yield from self._emit_final_report(state)

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

            channel = channel_map.get(target_task_id) if target_task_id is not None else None
            if channel:
                payload.setdefault("step", channel["step"])
                payload["stream_token"] = channel["token"]
            if step_override is not None:
                payload["step"] = step_override

            event_queue.put(payload)

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
                logger.exception("任务执行失败", exc_info=exc)
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

    def _emit_final_report(self, state: SummaryState) -> Iterator[dict[str, Any]]:
        final_step = len(state.todo_items) + 1
        try:
            report = self._reporting.generate_report(state)
        except Exception as exc:
            logger.exception("报告生成失败，将使用任务摘要兜底: %s", exc)
            summaries = "\n\n".join(
                f"### {t.title}\n{t.summary or '暂无摘要'}"
                for t in state.todo_items
            )
            report = f"## 研究摘要（报告生成失败，使用任务摘要兜底）\n\n{summaries}"

        yield from self._drain_tool_events(state, step=final_step)
        state.structured_report = report
        state.running_summary = report

        note_event = self._persist_final_report(state, report)
        if note_event:
            yield note_event

        yield {
            "type": "final_report",
            "report": report,
            "note_id": state.report_note_id,
            "note_path": state.report_note_path,
        }
        yield {"type": "done"}
