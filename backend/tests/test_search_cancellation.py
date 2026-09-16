from threading import Event, Lock

import pytest

from config import Configuration, SearchAPI
from models import SummaryState, TodoItem
from services.cancellation import ResearchCancelled
from services.search_backends import FallbackSearchBackend, SearchOutcome
from services.task_executor import TaskExecutor


@pytest.mark.parametrize("cancel_at", ["factory", "failure", "success", "exception"])
@pytest.mark.parametrize("injected", [True, False])
def test_executor_stops_search_chain_on_cancellation(monkeypatch, cancel_at, injected):
    config = Configuration(
        search_api=SearchAPI.TAVILY,
        search_fallback_chain=[SearchAPI.DUCKDUCKGO],
        enable_notes=False,
    )
    stop = Event()
    calls = []
    created = []
    finished = Event()

    class Backend:
        def search(self, query, *, config, loop_count):
            calls.append(query)
            if cancel_at == "exception":
                raise ResearchCancelled("cancelled by backend")
            stop.set()
            if cancel_at == "failure":
                raise RuntimeError("provider failed after cancellation")
            return SearchOutcome({"results": []}, [], None, "tavily")

    def create(name):
        created.append(name)
        if cancel_at == "factory":
            stop.set()
        return Backend()

    monkeypatch.setattr("services.search_backends.create_search_backend", create)
    # Run synchronously so cancellation cannot be hidden by the caller's polling loop.
    def call(fn, **kwargs):
        try:
            return fn()
        finally:
            finished.set()

    executor = TaskExecutor(
        config=config, summarizer=None, state_lock=Lock(),
        drain_tool_events=lambda *args, **kwargs: [],
        search_backend=FallbackSearchBackend(config) if injected else None,
    )
    monkeypatch.setattr(executor, "_call_with_timeout", call)
    state = SummaryState(research_topic="agent")
    task = TodoItem(id=1, title="agent", intent="learn", query="agent")
    events = list(executor.execute(state, task, emit_stream=True, stop_event=stop))

    assert finished.is_set()
    assert created == ["tavily"]
    assert calls == ([] if cancel_at == "factory" else ["agent"])
    assert task.status == "cancelled"
    assert events[-1]["status"] == "cancelled"
    assert state.web_research_results == []
    assert state.sources_gathered == []


def test_pre_cancelled_chain_does_not_create_backend(monkeypatch):
    config = Configuration(enable_notes=False)
    stop = Event()
    stop.set()
    created = []
    monkeypatch.setattr("services.search_backends.create_search_backend", created.append)
    with pytest.raises(ResearchCancelled):
        FallbackSearchBackend(config).search_with_cancellation(
            "agent", config=config, loop_count=0, stop_event=stop,
        )
    assert created == []
