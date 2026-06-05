from __future__ import annotations

import pytest

from models import SummaryState, TodoItem
from services.final_report_generator import FinalReportGenerator


class FakeReporting:
    def __init__(self, report: str | None = None, fail: Exception | None = None) -> None:
        self.report = report or "# 正常报告"
        self.fail = fail
        self.calls: list[SummaryState] = []

    def generate_report(self, state: SummaryState) -> str:
        self.calls.append(state)
        if self.fail:
            raise self.fail
        return self.report


def test_final_report_generator_returns_reporting_output() -> None:
    state = SummaryState(research_topic="AI Agent")
    state.todo_items = [TodoItem(id=1, title="任务一", intent="研究", query="agent", summary="摘要")]
    reporting = FakeReporting("# 报告")

    generator = FinalReportGenerator(reporting=reporting)

    assert generator.generate(state) == "# 报告"
    assert reporting.calls == [state]


def test_final_report_generator_falls_back_to_task_summaries_when_reporting_fails() -> None:
    state = SummaryState(research_topic="AI Agent")
    state.todo_items = [TodoItem(id=1, title="任务一", intent="研究", query="agent", summary="摘要")]
    generator = FinalReportGenerator(reporting=FakeReporting(fail=RuntimeError("boom")))

    report = generator.generate(state)

    assert "报告生成失败" in report
    assert "### 任务一" in report
    assert "摘要" in report
