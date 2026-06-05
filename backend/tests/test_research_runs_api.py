from __future__ import annotations

from main import create_app
from services.research_run_store import InMemoryResearchRunStore


def test_research_run_endpoint_reads_shared_app_run_store() -> None:
    app = create_app()
    run_store = app.state.run_store
    assert isinstance(run_store, InMemoryResearchRunStore)

    run_store.start_run(run_id="run-api-001", topic="AI Agent")
    run_store.record_event(
        "run-api-001",
        {"type": "status", "run_id": "run-api-001", "timestamp": "2026-06-05T00:00:00Z"},
    )
    run_store.complete_run("run-api-001")

    route = next(route for route in app.routes if getattr(route, "path", "") == "/research/runs/{run_id}")
    response = route.endpoint("run-api-001")

    assert response["run_id"] == "run-api-001"
    assert response["topic"] == "AI Agent"
    assert response["status"] == "completed"
    assert response["events"] == [
        {"type": "status", "run_id": "run-api-001", "timestamp": "2026-06-05T00:00:00Z"}
    ]
