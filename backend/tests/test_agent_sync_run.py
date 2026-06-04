from __future__ import annotations

from models import SummaryState, TodoItem
from agent import DeepResearchAgent


class FakeTaskExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[SummaryState, TodoItem, bool, int | None]] = []
        self.last_search_notices: list[str] = []

    def execute(self, state: SummaryState, task: TodoItem, *, emit_stream: bool, step: int | None = None):
        self.calls.append((state, task, emit_stream, step))
        task.status = "completed"
        task.summary = "同步任务摘要"
        state.web_research_results.append("同步上下文")
        state.sources_gathered.append("同步来源")
        yield from ()


class FakeReporting:
    def __init__(self) -> None:
        self.calls: list[SummaryState] = []

    def generate_report(self, state: SummaryState) -> str:
        self.calls.append(state)
        summaries = [task.summary for task in state.todo_items]
        return "最终报告: " + ", ".join(summary or "空摘要" for summary in summaries)


def test_sync_run_iterates_task_execution_generator_for_provided_tasks() -> None:
    agent = object.__new__(DeepResearchAgent)
    task_executor = FakeTaskExecutor()
    reporting = FakeReporting()
    persisted: list[tuple[SummaryState, str]] = []

    agent.task_executor = task_executor
    agent.reporting = reporting
    agent._drain_tool_events = lambda state, step=None: []
    agent._persist_final_report = lambda state, report: persisted.append((state, report))

    task = TodoItem(id=1, title="任务一", intent="验证同步执行", query="agent sync run")

    result = agent.run("AI Agent", todo_items=[task])

    assert len(task_executor.calls) == 1
    assert task_executor.calls[0][1] is task
    assert task_executor.calls[0][2] is False
    assert task.status == "completed"
    assert task.summary == "同步任务摘要"
    assert result.report_markdown == "最终报告: 同步任务摘要"
    assert result.todo_items == [task]
    assert reporting.calls
    assert persisted[0][1] == "最终报告: 同步任务摘要"
