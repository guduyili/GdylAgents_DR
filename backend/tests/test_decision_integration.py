import json
from threading import Lock

import pytest

from config import Configuration
from models import SummaryState, TodoItem
from services.task_executor import TaskExecutor
from services.task_serializer import serialize_task


class Summarizer:
    def summarize_task(self, state, task, context):
        assert "https://example.com/first" in context
        assert "https://example.com/second" in context
        return "combined summary"

    def stream_task_summary(self, state, task, context):
        summary = self.summarize_task(state, task, context)
        return iter([summary]), lambda: summary


@pytest.mark.parametrize("stream", [False, True])
def test_decision_mode_executes_multiple_searches_and_summarizes_once(stream):
    calls = []
    actions = iter([
        {"action": "search", "query": "first", "reason": "collect"},
        {"action": "search", "query": "second", "reason": "compare"},
        {"action": "finish", "reason": "done"},
    ])
    def search(query, config, loop_count):
        calls.append(query)
        return {"results": [{"url": f"https://example.com/{query}", "content": query}]}, [], None, "fake"
    executor = TaskExecutor(
        config=Configuration(task_execution_mode="decision", enable_notes=False, enable_fact_check=False),
        summarizer=Summarizer(), state_lock=Lock(), drain_tool_events=lambda *args, **kwargs: [],
        search_dispatcher=search, decision_provider=lambda *args: next(actions),
        context_preparer=lambda payload, *args: ("two sources", json.dumps(payload)),
    )
    state = SummaryState(research_topic="topic")
    task = TodoItem(id=1, title="task", intent="learn", query="initial")
    events = list(executor.execute(state, task, emit_stream=stream))
    assert calls == ["first", "second"]
    assert task.status == "completed" and task.summary == "combined summary"
    assert task.decision_stop_reason == "finish"
    assert len(state.web_research_results) == 1
    assert serialize_task(task)["decision_trace"][-1]["stop_reason"] == "finish"
    if stream:
        assert len([e for e in events if e.get("source") == "decision_loop"]) == 6


def test_invalid_model_action_fails_task_without_searching():
    calls = []
    executor = TaskExecutor(
        config=Configuration(task_execution_mode="decision", enable_notes=False),
        summarizer=None, state_lock=Lock(), drain_tool_events=lambda *args, **kwargs: [],
        decision_provider=lambda *args: {"action": "shell", "reason": "bad"},
        search_dispatcher=lambda *args: calls.append(args),
    )
    task = TodoItem(id=1, title="task", intent="learn", query="initial")
    events = list(executor.execute(SummaryState(research_topic="topic"), task, emit_stream=True))
    assert not calls
    assert task.status == "failed"
    assert task.decision_stop_reason == "invalid_action"
    assert events[-1]["status"] == "failed"


def test_factory_wires_model_decider_for_decision_mode():
    from services.research_services_factory import create_research_services
    from services.task_decider import LLMTaskDecider
    services = create_research_services(Configuration(task_execution_mode="decision", enable_notes=False))
    assert isinstance(services.task_executor._decision_provider, LLMTaskDecider)
