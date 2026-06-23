from __future__ import annotations

from models import SummaryState, TodoItem
from services.review_service import ReviewService


def test_review_service_flags_short_report_without_references() -> None:
    state = SummaryState(research_topic="AI Agent")
    state.todo_items = [
        TodoItem(id=1, title="任务一", intent="研究", query="agent", status="completed", sources_summary="来源 A")
    ]
    state.sources_gathered = ["来源 A"]

    result = ReviewService(min_report_chars=500).review(state, "# 短报告\n\n内容很少")

    assert result.passed is False
    assert result.score < 100
    assert any("过短" in issue for issue in result.issues)
    assert any("参考" in suggestion for suggestion in result.suggestions)


def test_review_service_passes_when_report_has_reference_section() -> None:
    state = SummaryState(research_topic="AI Agent")
    state.todo_items = [
        TodoItem(
            id=1,
            title="任务一",
            intent="研究",
            query="agent",
            status="completed",
            sources_summary="来源 A",
            summary="较长摘要" * 80,
        )
    ]
    state.sources_gathered = ["来源 A"]

    report = "# AI Agent\n\n" + ("正文内容。" * 120) + "\n\n## 参考\n\n- 来源 A"
    result = ReviewService(min_report_chars=200).review(state, report)

    assert result.passed is True
    assert result.score >= 80
    assert not result.issues