from __future__ import annotations

from pathlib import Path

import pytest

from services.research_run_store import SQLiteResearchRunStore


def test_sqlite_research_run_store_persists_run_across_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "research_runs.sqlite3"
    first = SQLiteResearchRunStore(db_path)
    first.start_run(run_id="run-001", topic="AI Agent")
    first.record_event("run-001", {"type": "status", "timestamp": "t1", "run_id": "run-001"})
    first.record_event("run-001", {"type": "tool_call", "timestamp": "t2", "run_id": "run-001", "task_run_id": "run-001:task:1"})
    first.complete_run("run-001")

    second = SQLiteResearchRunStore(db_path)

    assert second.get_run("run-001") == {
        "run_id": "run-001",
        "topic": "AI Agent",
        "status": "completed",
        "events": [
            {"type": "status", "timestamp": "t1", "run_id": "run-001"},
            {"type": "tool_call", "timestamp": "t2", "run_id": "run-001", "task_run_id": "run-001:task:1"},
        ],
    }


def test_sqlite_research_run_store_returns_none_for_missing_run(tmp_path: Path) -> None:
    store = SQLiteResearchRunStore(tmp_path / "research_runs.sqlite3")

    assert store.get_run("missing") is None


def test_sqlite_research_run_store_ignores_events_for_missing_run(tmp_path: Path) -> None:
    store = SQLiteResearchRunStore(tmp_path / "research_runs.sqlite3")

    store.record_event("missing", {"type": "status", "run_id": "missing"})

    assert store.get_run("missing") is None


def test_sqlite_research_run_store_replaces_existing_run_and_clears_old_events(tmp_path: Path) -> None:
    store = SQLiteResearchRunStore(tmp_path / "research_runs.sqlite3")
    store.start_run(run_id="run-001", topic="old topic")
    store.record_event("run-001", {"type": "status", "message": "old", "run_id": "run-001"})

    store.start_run(run_id="run-001", topic="new topic")
    store.record_event("run-001", {"type": "status", "message": "new", "run_id": "run-001"})

    assert store.get_run("run-001") == {
        "run_id": "run-001",
        "topic": "new topic",
        "status": "running",
        "events": [
            {"type": "status", "message": "new", "run_id": "run-001"},
        ],
    }


def test_sqlite_research_run_store_rejects_non_json_event_payload(tmp_path: Path) -> None:
    store = SQLiteResearchRunStore(tmp_path / "research_runs.sqlite3")
    store.start_run(run_id="run-001", topic="AI Agent")

    with pytest.raises(TypeError):
        store.record_event("run-001", {"type": "status", "bad": object()})
