from __future__ import annotations

from services.research_run_store import InMemoryResearchRunStore


def test_in_memory_research_run_store_returns_run_timeline() -> None:
    store = InMemoryResearchRunStore()
    store.start_run(run_id="run-001", topic="AI Agent")
    store.record_event("run-001", {"type": "status", "timestamp": "t1", "run_id": "run-001"})
    store.record_event("run-001", {"type": "tool_call", "timestamp": "t2", "run_id": "run-001"})
    store.complete_run("run-001", phase_durations={"planning": 10, "total": 100})

    snapshot = store.get_run("run-001")

    assert snapshot == {
        "run_id": "run-001",
        "topic": "AI Agent",
        "status": "completed",
        "phase_durations": {"planning": 10, "total": 100},
        "events": [
            {"type": "status", "timestamp": "t1", "run_id": "run-001"},
            {"type": "tool_call", "timestamp": "t2", "run_id": "run-001"},
        ],
    }


def test_in_memory_research_run_store_cancel_run() -> None:
    store = InMemoryResearchRunStore()
    store.start_run(run_id="run-001", topic="AI Agent")
    store.cancel_run("run-001", phase_durations={"total": 12})

    snapshot = store.get_run("run-001")

    assert snapshot == {
        "run_id": "run-001",
        "topic": "AI Agent",
        "status": "cancelled",
        "phase_durations": {"total": 12},
        "events": [],
    }


def test_in_memory_research_run_store_returns_none_for_missing_run() -> None:
    store = InMemoryResearchRunStore()

    assert store.get_run("missing") is None
