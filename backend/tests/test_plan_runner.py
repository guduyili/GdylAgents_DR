from __future__ import annotations

from models import TodoItem
from services.plan_runner import PlanRunner


class FakePlanner:
    def __init__(self, planned: list[TodoItem] | None = None) -> None:
        self.planned = planned or []
        self.fallback_called = False

    def plan_todo_list(self, state):
        return self.planned

    def create_fallback_task(self, state):
        self.fallback_called = True
        return TodoItem(id=99, title="兜底任务", intent="兜底", query=state.research_topic)


def test_plan_runner_returns_planned_tasks_and_drains_tool_events() -> None:
    task = TodoItem(id=1, title="任务一", intent="研究", query="agent")
    drained = []
    runner = PlanRunner(
        planner=FakePlanner([task]),
        drain_tool_events=lambda state, step=None: drained.append((state, step)) or [],
    )

    assert runner.plan("AI Agent") == [task]
    assert drained


def test_plan_runner_uses_fallback_when_planner_returns_empty() -> None:
    planner = FakePlanner([])
    runner = PlanRunner(planner=planner, drain_tool_events=lambda state, step=None: [])

    tasks = runner.plan("AI Agent")

    assert planner.fallback_called is True
    assert tasks[0].id == 99
