from __future__ import annotations

from models import SummaryStateOutput, TodoItem
from agent import DeepResearchAgent


class FakeSyncRunner:
    def __init__(self, output: SummaryStateOutput) -> None:
        self.output = output
        self.calls: list[tuple[str, list[TodoItem] | None]] = []

    def run(self, topic: str, todo_items: list[TodoItem] | None = None) -> SummaryStateOutput:
        self.calls.append((topic, todo_items))
        if todo_items:
            todo_items[0].status = "completed"
            todo_items[0].summary = "同步任务摘要"
        return self.output


class FakeServices:
    def __init__(self, sync_runner: FakeSyncRunner) -> None:
        self.sync_runner = sync_runner


def test_sync_run_delegates_to_sync_runner_for_provided_tasks() -> None:
    task = TodoItem(id=1, title="任务一", intent="验证同步执行", query="agent sync run")
    output = SummaryStateOutput(
        running_summary="最终报告: 同步任务摘要",
        report_markdown="最终报告: 同步任务摘要",
        todo_items=[task],
    )
    sync_runner = FakeSyncRunner(output)
    agent = DeepResearchAgent(services=FakeServices(sync_runner))

    result = agent.run("AI Agent", todo_items=[task])

    assert sync_runner.calls == [("AI Agent", [task])]
    assert task.status == "completed"
    assert task.summary == "同步任务摘要"
    assert result.report_markdown == "最终报告: 同步任务摘要"
    assert result.todo_items == [task]
