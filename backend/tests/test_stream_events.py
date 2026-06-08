from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.stream_events import normalize_stream_event


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
