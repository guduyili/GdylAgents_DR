from __future__ import annotations

from config import Configuration
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
