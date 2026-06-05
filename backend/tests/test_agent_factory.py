from __future__ import annotations

from config import Configuration
from services.agent_factory import AgentFactory


class FakeAgent:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class FakeLLMCreator:
    def __init__(self) -> None:
        self.calls: list[tuple[Configuration, str | None]] = []

    def __call__(self, config: Configuration, *, model_override: str | None = None):
        self.calls.append((config, model_override))
        return {"model_override": model_override}


def test_agent_factory_uses_default_llm_for_main_model_and_override_for_report_model() -> None:
    config = Configuration(llm_model_id="main-model", report_model_id="report-model", enable_notes=False)
    default_llm = {"model": "main"}
    llm_creator = FakeLLMCreator()
    listener = lambda payload: None

    factory = AgentFactory(
        config=config,
        default_llm=default_llm,
        tools_registry=None,
        tool_call_listener=listener,
        llm_creator=llm_creator,
        agent_class=FakeAgent,
    )

    todo_agent = factory.create_todo_agent()
    report_agent = factory.create_report_agent()
    summarizer = factory.create_summarizer_factory()()

    assert todo_agent.kwargs["llm"] is default_llm
    assert summarizer.kwargs["llm"] is default_llm
    assert report_agent.kwargs["llm"] == {"model_override": "report-model"}
    assert llm_creator.calls == [(config, "report-model")]
    assert todo_agent.kwargs["tool_call_listener"] is listener
    assert todo_agent.kwargs["enable_tool_calling"] is False
