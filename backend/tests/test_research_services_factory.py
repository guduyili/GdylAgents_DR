from __future__ import annotations

from pathlib import Path

from config import Configuration
from services.research_run_store import InMemoryResearchRunStore, SQLiteResearchRunStore
from services.research_services_factory import ResearchServices, create_research_services


def test_create_research_services_wires_core_runners_with_notes_disabled() -> None:
    config = Configuration(enable_notes=False)

    services = create_research_services(config)

    assert isinstance(services, ResearchServices)
    assert services.config is config
    assert services.note_tool is None
    assert services.tools_registry is None
    assert services.sync_runner is not None
    assert services.stream_runner is not None
    assert services.planner is not None
    assert services.task_executor is not None
    assert isinstance(services.run_store, InMemoryResearchRunStore)


def test_create_research_services_uses_sqlite_run_store_when_configured(tmp_path: Path) -> None:
    db_path = tmp_path / "runs.sqlite3"
    config = Configuration(
        enable_notes=False,
        run_store_backend="sqlite",
        run_store_db_path=str(db_path),
    )

    services = create_research_services(config)

    assert isinstance(services.run_store, SQLiteResearchRunStore)
    services.run_store.start_run(run_id="run-001", topic="AI Agent")
    services.run_store.record_event("run-001", {"type": "status", "run_id": "run-001"})

    reloaded = SQLiteResearchRunStore(db_path)
    assert reloaded.get_run("run-001") == {
        "run_id": "run-001",
        "topic": "AI Agent",
        "status": "running",
        "events": [{"type": "status", "run_id": "run-001"}],
    }
