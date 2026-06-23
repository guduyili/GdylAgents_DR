from __future__ import annotations

import pytest

from config import Configuration
from services.agent_factory import AgentFactory
from services.agent_registry import AgentRegistry


class FakeAgent:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


def test_agent_registry_registers_and_creates_roles() -> None:
    registry = AgentRegistry()
    registry.register("alpha", lambda: "agent-alpha")
    registry.register("beta", lambda: "agent-beta")

    assert registry.roles() == ["alpha", "beta"]
    assert registry.create("alpha") == "agent-alpha"
    assert registry.has_role("beta") is True

    with pytest.raises(KeyError):
        registry.create("missing")


def test_agent_factory_builds_default_pipeline_registry() -> None:
    config = Configuration(llm_model_id="main-model", report_model_id="report-model", enable_notes=False)
    factory = AgentFactory(
        config=config,
        default_llm={"model": "main"},
        tools_registry=None,
        tool_call_listener=lambda payload: None,
        agent_class=FakeAgent,
    )

    registry = factory.create_registry()

    assert registry.roles() == ["planner", "reporter", "summarizer"]
    planner = registry.create("planner")
    reporter = registry.create("reporter")
    summarizer = registry.create("summarizer")

    assert planner.kwargs["name"] == "研究规划专家"
    assert reporter.kwargs["name"] == "报告撰写专家"
    assert summarizer.kwargs["name"] == "任务总结专家"