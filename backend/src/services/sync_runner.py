"""同步运行服务：负责非 SSE 的完整研究流程编排。"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from models import SummaryState, SummaryStateOutput, TodoItem
from services.final_report_generator import FinalReportGenerator
from services.planner import PlanningService
from services.task_executor import TaskExecutor

logger = logging.getLogger(__name__)


class DrainToolEvents(Protocol):
    def __call__(
        self,
        state: SummaryState,
        *,
        step: int | None = None,
    ) -> list[dict[str, Any]]: ...


class PersistFinalReport(Protocol):
    def __call__(self, state: SummaryState, report: str) -> dict[str, Any] | None: ...


class ReportRetrieverLike(Protocol):
    def retrieve(self, query: str, *, top_k: int | None = None) -> list[Any]: ...

    def format_context(self, chunks: list[Any]) -> str: ...

    def invalidate(self) -> None: ...


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
        research_mode: str = "deep",
        report_retriever: ReportRetrieverLike | None = None,
    ) -> None:
        self._planner = planner
        self._task_executor = task_executor
        self._final_report_generator = final_report_generator
        self._drain_tool_events = drain_tool_events
        self._persist_final_report = persist_final_report
        self._research_mode = research_mode
        self._report_retriever = report_retriever

    def run(self, topic: str, todo_items: list[TodoItem] | None = None) -> SummaryStateOutput:
        state = SummaryState(research_topic=topic)

        if todo_items is not None:
            state.todo_items = todo_items
        elif self._research_mode == "quick":
            topic = state.research_topic.strip()
            title = f"快速浏览：{topic[:40]}" if len(topic) > 40 else f"快速浏览：{topic}"
            state.todo_items = [
                TodoItem(
                    id=1,
                    title=title,
                    intent="快速获取主题概览与要点摘要",
                    query=topic,
                )
            ]
        else:
            self._attach_rag_context(state, topic)
            state.todo_items = self._planner.plan_todo_list(state)
            self._drain_tool_events(state)

        if not state.todo_items:
            state.todo_items = [self._planner.create_fallback_task(state)]

        for task in state.todo_items:
            for _event in self._task_executor.execute(state, task, emit_stream=False):
                # 同步模式不返回中间事件，但必须消耗生成器以触发执行副作用。
                pass

        if self._research_mode == "quick":
            report = self._build_quick_report(state)
        else:
            report = self._final_report_generator.generate(state)
        self._drain_tool_events(state)
        state.structured_report = report
        state.running_summary = report
        self._persist_final_report(state, report)
        if self._report_retriever is not None:
            try:
                self._report_retriever.invalidate()
            except Exception:
                logger.exception("SyncRunner RAG invalidate 失败")

        return SummaryStateOutput(
            running_summary=report,
            report_markdown=report,
            todo_items=state.todo_items,
        )

    def _attach_rag_context(self, state: SummaryState, topic: str) -> None:
        if self._report_retriever is None:
            return
        try:
            hits = self._report_retriever.retrieve(topic)
            state.prior_research_context = self._report_retriever.format_context(hits) or None
        except Exception:
            logger.exception("SyncRunner RAG 检索失败")
            state.prior_research_context = None

    @staticmethod
    def _build_quick_report(state: SummaryState) -> str:
        lines = [f"# {state.research_topic}", ""]
        for task in state.todo_items:
            lines.append(f"## {task.title}")
            lines.append(task.summary or "暂无摘要")
            if task.sources_summary:
                lines.extend(["", "### 来源", task.sources_summary])
        return "\n\n".join(lines).strip()
