"""规划运行服务：负责仅规划任务的入口逻辑。"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from models import SummaryState, TodoItem
from services.planner import PlanningService

logger = logging.getLogger(__name__)


class DrainToolEvents(Protocol):
    def __call__(
        self,
        state: SummaryState,
        *,
        step: int | None = None,
    ) -> list[dict[str, Any]]: ...


class ReportRetrieverLike(Protocol):
    def retrieve(self, query: str, *, top_k: int | None = None) -> list[Any]: ...

    def format_context(self, chunks: list[Any]) -> str: ...


class PlanRunner:
    """执行只规划、不搜索总结的研究任务规划流程。"""

    def __init__(
        self,
        *,
        planner: PlanningService,
        drain_tool_events: DrainToolEvents,
        report_retriever: ReportRetrieverLike | None = None,
    ) -> None:
        self._planner = planner
        self._drain_tool_events = drain_tool_events
        self._report_retriever = report_retriever

    def plan(self, topic: str) -> list[TodoItem]:
        state = SummaryState(research_topic=topic)
        self._attach_rag_context(state, topic)
        todo_items = self._planner.plan_todo_list(state)
        self._drain_tool_events(state)
        if not todo_items:
            todo_items = [self._planner.create_fallback_task(state)]
        return todo_items

    def _attach_rag_context(self, state: SummaryState, topic: str) -> None:
        if self._report_retriever is None:
            return
        try:
            hits = self._report_retriever.retrieve(topic)
            state.prior_research_context = self._report_retriever.format_context(hits) or None
            if hits:
                logger.info("PlanRunner RAG 命中 %d 条片段 topic=%s", len(hits), topic[:80])
        except Exception:
            logger.exception("PlanRunner RAG 检索失败，继续无历史上下文规划")
            state.prior_research_context = None
