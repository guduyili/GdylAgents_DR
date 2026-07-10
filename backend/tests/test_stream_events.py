from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.stream_events import build_stream_event, normalize_stream_event


def test_normalize_stream_event_adds_observability_and_keeps_known_event_fields() -> None:
    event = normalize_stream_event(
        {
            "type": "task_status",
            "task_id": 1,
            "status": "completed",
            "title": "任务一",
            "summary": "摘要",
            "stream_token": "task_1",
        },
        run_id="run-001",
        timestamp="2026-06-08T12:00:00Z",
    )

    assert event == {
        "type": "task_status",
        "run_id": "run-001",
        "timestamp": "2026-06-08T12:00:00Z",
        "task_id": 1,
        "status": "completed",
        "title": "任务一",
        "summary": "摘要",
        "stream_token": "task_1",
    }


def test_normalize_stream_event_rejects_unknown_public_event_type() -> None:
    with pytest.raises(ValidationError):
        normalize_stream_event(
            {"type": "not_a_real_event"},
            run_id="run-001",
            timestamp="2026-06-08T12:00:00Z",
        )


def test_normalize_stream_event_rejects_missing_required_event_field() -> None:
    with pytest.raises(ValidationError):
        normalize_stream_event(
            {"type": "final_report"},
            run_id="run-001",
            timestamp="2026-06-08T12:00:00Z",
        )


def test_normalize_stream_event_keeps_internal_task_done_unvalidated() -> None:
    event = normalize_stream_event(
        {"type": "__task_done__", "task_id": 1},
        run_id="run-001",
        timestamp="2026-06-08T12:00:00Z",
    )

    assert event == {
        "type": "__task_done__",
        "run_id": "run-001",
        "timestamp": "2026-06-08T12:00:00Z",
        "task_id": 1,
    }


def test_build_stream_event_validates_partial_payload_without_observability_fields() -> None:
    event = build_stream_event(
        {
            "type": "task_summary_chunk",
            "task_id": 2,
            "content": "chunk",
            "step": 2,
            "source": "summarizer",
        }
    )

    assert event == {
        "type": "task_summary_chunk",
        "task_id": 2,
        "content": "chunk",
        "step": 2,
        "source": "summarizer",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "status", "message": "初始化研究流程", "source": "stream_runner"},
        {
            "type": "todo_list",
            "tasks": [{"title": "任务一", "intent": "研究"}],
            "step": 0,
            "source": "stream_runner",
        },
        {
            "type": "sources",
            "task_id": 1,
            "latest_sources": "来源",
            "raw_context": "上下文",
            "backend": "duckduckgo",
            "step": 1,
            "source": "task_executor",
        },
        {
            "type": "task_summary_chunk",
            "task_id": 1,
            "content": "摘要片段",
            "step": 1,
            "source": "summarizer",
        },
        {
            "type": "task_status",
            "task_id": 1,
            "status": "completed",
            "title": "任务一",
            "summary": "摘要",
            "step": 1,
            "source": "task_executor",
        },
        {
            "type": "tool_call",
            "event_id": 1,
            "tool": "note",
            "agent": "研究规划专家",
            "task_id": 1,
            "source": "tool",
        },
        {
            "type": "report_note",
            "note_id": "note_123",
            "title": "研究报告",
            "content": "正文",
            "source": "report_persistence",
        },
        {
            "type": "final_report",
            "report": "# 报告",
            "source": "reporter",
        },
        {
            "type": "review_result",
            "passed": True,
            "score": 90,
            "issues": [],
            "suggestions": ["可补充参考章节"],
            "source": "review_service",
        },
        {
            "type": "fact_check_result",
            "task_id": 1,
            "passed": True,
            "score": 88,
            "matched_sources": ["https://example.com"],
            "warnings": [],
            "missing_terms": [],
            "source": "fact_check_service",
        },
        {
            "type": "skill_loaded",
            "task_id": 1,
            "skill_name": "Deep Research",
            "skill_description": "Guide deep research",
            "preview": "Skill preview",
            "source": "skill_loader",
        },
        {"type": "phase_duration", "phase": "search", "duration_ms": 1200, "source": "stream_runner"},
        {"type": "done", "source": "stream_runner"},
        {
            "type": "cancelled",
            "message": "研究已取消",
            "source": "stream_runner",
        },
        {
            "type": "task_status",
            "task_id": 2,
            "status": "cancelled",
            "title": "任务二",
            "error": "任务已取消",
            "source": "task_executor",
        },
        {"type": "error", "detail": "失败原因"},
    ],
)
def test_all_public_stream_event_types_pass_build_and_normalize(payload: dict) -> None:
    built = build_stream_event(payload)
    normalized = normalize_stream_event(
        built,
        run_id="run-smoke-001",
        timestamp="2026-06-13T12:00:00Z",
    )

    assert normalized["type"] == payload["type"]
    assert normalized["run_id"] == "run-smoke-001"
    assert normalized["timestamp"] == "2026-06-13T12:00:00Z"