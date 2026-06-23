from __future__ import annotations

from models import TodoItem
from services.fact_check_service import FactCheckService


def test_fact_check_service_passes_when_summary_aligns_with_sources() -> None:
    task = TodoItem(
        id=1,
        title="AI Agent",
        intent="研究",
        query="agent",
        summary="AI Agent 架构在 2026 年持续演进，多模态能力成为关键突破方向。",
        sources_summary="* AI Agent 架构 : https://example.com/agent\n信息内容: agent architecture",
    )

    result = FactCheckService().check(task)

    assert result.score >= 60
    assert result.matched_sources


def test_fact_check_service_warns_when_sources_missing() -> None:
    task = TodoItem(
        id=1,
        title="AI Agent",
        intent="研究",
        query="agent",
        summary="短摘要",
        sources_summary="",
    )

    result = FactCheckService().check(task)

    assert result.passed is False
    assert result.warnings