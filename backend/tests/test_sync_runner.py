from __future__ import annotations

from models import SummaryState, SummaryStateOutput, TodoItem
from services.sync_runner import SyncRunner


class FakePlanner:
    def __init__(self, planned: list[TodoItem] | None = None) -> None:
        self.planned = planned or []
        self.plan_calls: list[SummaryState] = []

    def plan_todo_list(self, state: SummaryState) -> list[TodoItem]:
        self.plan_calls.append(state)
        return self.planned

    def create_fallback_task(self, state: SummaryState) -> TodoItem:
        return TodoItem(id=99, title="兜底任务", intent="兜底", query=state.research_topic)


class FakeTaskExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[SummaryState, TodoItem, bool, int | None]] = []
        self.last_search_notices: list[str] = []

    def execute(self, state: SummaryState, task: TodoItem, *, emit_stream: bool, step: int | None = None):
        self.calls.append((state, task, emit_stream, step))
        task.status = "completed"
        task.summary = "任务摘要"
        state.web_research_results.append("上下文")
        yield from ()


class FakeFinalReportGenerator:
    def __init__(self, report: str = "最终报告") -> None:
        self.report = report
        self.calls: list[SummaryState] = []

    def generate(self, state: SummaryState) -> str:
        self.calls.append(state)
        return self.report


def test_sync_runner_executes_tasks_generates_persists_and_returns_output() -> None:
    task = TodoItem(id=1, title="任务一", intent="研究", query="agent")
    task_executor = FakeTaskExecutor()
    final_report_generator = FakeFinalReportGenerator("# 报告")
    drained: list[tuple[SummaryState, int | None]] = []
    persisted: list[tuple[SummaryState, str]] = []

    runner = SyncRunner(
        planner=FakePlanner(),
        task_executor=task_executor,
        final_report_generator=final_report_generator,
        drain_tool_events=lambda state, step=None: drained.append((state, step)) or [],
        persist_final_report=lambda state, report: persisted.append((state, report)) or None,
    )

    result = runner.run("AI Agent", todo_items=[task])

    assert isinstance(result, SummaryStateOutput)
    assert result.report_markdown == "# 报告"
    assert result.running_summary == "# 报告"
    assert result.todo_items == [task]
    assert task_executor.calls[0][1] is task
    assert task_executor.calls[0][2] is False
    assert task.summary == "任务摘要"
    assert final_report_generator.calls
    assert persisted[0][1] == "# 报告"
    assert drained
