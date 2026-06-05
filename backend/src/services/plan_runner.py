"""规划运行服务：负责仅规划任务的入口逻辑。"""

from __future__ import annotations

from typing import Any, Protocol

from models import SummaryState, TodoItem
from services.planner import PlanningService


class DrainToolEvents(Protocol):
    def __call__(
        self,
        state: SummaryState,
        *,
        step: int | None = None,
    ) -> list[dict[str, Any]]: ...


class PlanRunner:
    """执行只规划、不搜索总结的研究任务规划流程。"""

    def __init__(self, *, planner: PlanningService, drain_tool_events: DrainToolEvents) -> None:
        self._planner = planner
        self._drain_tool_events = drain_tool_events

    def plan(self, topic: str) -> list[TodoItem]:
        state = SummaryState(research_topic=topic)
        todo_items = self._planner.plan_todo_list(state)
        self._drain_tool_events(state)
        if not todo_items:
            todo_items = [self._planner.create_fallback_task(state)]
        return todo_items
