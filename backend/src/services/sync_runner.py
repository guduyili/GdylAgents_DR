"""同步运行服务：负责非 SSE 的完整研究流程编排。"""

from __future__ import annotations

from typing import Any, Iterator, Protocol

from models import SummaryState, SummaryStateOutput, TodoItem
from services.final_report_generator import FinalReportGenerator
from services.planner import PlanningService
from services.task_executor import TaskExecutor


class DrainToolEvents(Protocol):
    def __call__(
        self,
        state: SummaryState,
        *,
        step: int | None = None,
    ) -> list[dict[str, Any]]: ...


class PersistFinalReport(Protocol):
    def __call__(self, state: SummaryState, report: str) -> dict[str, Any] | None: ...


class SyncRunner:
    """同步执行研究流程并返回最终结构化输出。"""

    def __init__(
        self,
        *,
        planner: PlanningService,
        task_executor: TaskExecutor,
        final_report_generator: FinalReportGenerator,
        drain_tool_events: DrainToolEvents,
        persist_final_report: PersistFinalReport,
    ) -> None:
        self._planner = planner
        self._task_executor = task_executor
        self._final_report_generator = final_report_generator
        self._drain_tool_events = drain_tool_events
        self._persist_final_report = persist_final_report

    def run(self, topic: str, todo_items: list[TodoItem] | None = None) -> SummaryStateOutput:
        state = SummaryState(research_topic=topic)

        if todo_items is not None:
            state.todo_items = todo_items
        else:
            state.todo_items = self._planner.plan_todo_list(state)
            self._drain_tool_events(state)

        if not state.todo_items:
            state.todo_items = [self._planner.create_fallback_task(state)]

        for task in state.todo_items:
            for _event in self._task_executor.execute(state, task, emit_stream=False):
                # 同步模式不返回中间事件，但必须消耗生成器以触发执行副作用。
                pass

        report = self._final_report_generator.generate(state)
        self._drain_tool_events(state)
        state.structured_report = report
        state.running_summary = report
        self._persist_final_report(state, report)

        return SummaryStateOutput(
            running_summary=report,
            report_markdown=report,
            todo_items=state.todo_items,
        )
