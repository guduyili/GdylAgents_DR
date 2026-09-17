from __future__ import annotations

import pytest

from models import TodoItem
from services.fact_check_service import FactCheckService


def test_fact_check_service_passes_when_summary_aligns_with_sources() -> None:
    task = TodoItem(
        id=1,
        title="AI Agent",
        intent="研究",
        query="agent",
        summary="Planning / retrieval / evidence / verification — 2026.",
        sources_summary="https://example.com/agent\nPLANNING RETRIEVAL EVIDENCE VERIFICATION",
    )

    result = FactCheckService().check(task)

    assert result.passed is True
    assert result.score == 100
    assert result.missing_terms == []
    assert result.warnings == []
    assert result.matched_sources


@pytest.mark.parametrize(
    ("source_text", "expected_missing", "expected_passed", "expected_score"),
    [
        (
            "Coastal tides change daily.",
            ["Planning", "retrieval", "evidence", "verification"],
            False,
            68,
        ),
        ("Planning retrieval evidence", ["verification"], True, 92),
        ("Planning retrieval", ["evidence", "verification"], False, 84),
    ],
    ids=["unrelated-source", "one-missing-term", "two-missing-terms"],
)
def test_fact_check_matches_terms_only_against_sources(
    source_text: str,
    expected_missing: list[str],
    expected_passed: bool,
    expected_score: int,
) -> None:
    task = TodoItem(
        id=1,
        title="Agent research",
        intent="研究",
        query="agent",
        summary="Planning / retrieval / evidence / verification — 2026.",
        sources_summary=f"https://example.com/article\n{source_text}",
    )

    result = FactCheckService().check(task)

    assert result.warnings == []  # A valid URL and sufficient length isolate term matching.
    assert result.missing_terms == expected_missing
    assert result.passed is expected_passed
    assert result.score == expected_score


@pytest.mark.parametrize("source_text", ["智能规划 信息检索 证据核对 结论验证", "潮汐变化 海洋观测"])
def test_fact_check_matches_chinese_terms_only_against_sources(source_text: str) -> None:
    task = TodoItem(
        id=1,
        title="研究",
        intent="核对",
        query="智能规划",
        summary="智能规划，信息检索，证据核对，结论验证。2026 年 09 月 16 日：12345678901234567890。",
        sources_summary=f"https://example.com/article\n{source_text}",
    )

    result = FactCheckService().check(task)

    expected_supported = source_text.startswith("智能规划")
    assert result.warnings == []
    assert result.passed is expected_supported
    assert result.missing_terms == ([] if expected_supported else ["智能规划", "信息检索", "证据核对", "结论验证"])


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
