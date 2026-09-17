from threading import Event, Lock
import sys
from types import SimpleNamespace

import pytest

from config import Configuration, SearchAPI
from models import SummaryState, TodoItem
from services.cancellation import ResearchCancelled
from services.search_backends import DuckDuckGoBackend, FallbackSearchBackend, SearchOutcome
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


@pytest.mark.parametrize("cancel_at", ["before", "enter", "failure", "empty", "success", "exception", "exit"])
def test_duckduckgo_cancellation_stops_internal_attempts(monkeypatch, cancel_at):
    config = Configuration(
        search_api=SearchAPI.DUCKDUCKGO, search_fallback_chain=[SearchAPI.TAVILY],
        search_timeout_seconds=2, enable_notes=False,
    )
    stop = Event()
    created, attempts, exits, timeouts = [], [], [], []
    now = [0.0]
    cancellation = ResearchCancelled("SDK cancelled")
    if cancel_at == "before":
        stop.set()

    class FakeDDGS:
        def __init__(self, *, timeout):
            timeouts.append(timeout)

        def __enter__(self):
            if cancel_at == "enter":
                stop.set()
            return self

        def __exit__(self, *args):
            exits.append(True)
            if cancel_at == "exit":
                stop.set()

        def text(self, query, *, max_results, backend):
            attempts.append(backend)
            if cancel_at == "exception":
                raise cancellation
            if cancel_at != "exit":
                stop.set()
            if cancel_at == "failure":
                raise RuntimeError("request failed")
            if cancel_at == "empty":
                return []
            return [{"title": "A", "href": "https://example.com"}]

    def create(name):
        created.append(name)
        now[0] += 1.75
        return DuckDuckGoBackend()

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
    monkeypatch.setattr("services.search_backends.create_search_backend", create)
    monkeypatch.setattr("services.search_backends.monotonic", lambda: now[0])
    with pytest.raises(ResearchCancelled) as error:
        FallbackSearchBackend(config).search_with_cancellation(
            "agent", config=config, loop_count=0, stop_event=stop,
        )
    assert created == ([] if cancel_at == "before" else ["duckduckgo"])
    assert attempts == ([] if cancel_at in {"before", "enter"} else ["lite"])
    assert timeouts == ([] if cancel_at == "before" else [0.25])
    assert len(exits) == len(timeouts)
    if cancel_at == "exception":
        assert error.value is cancellation


@pytest.mark.parametrize("cancel_at", ["before", "success"])
def test_direct_duckduckgo_adapter_honors_cancellation(monkeypatch, cancel_at):
    stop = Event()
    if cancel_at == "before":
        stop.set()
    calls = []

    class FakeDDGS:
        def __init__(self, *, timeout):
            calls.append(timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def text(self, *args, **kwargs):
            stop.set()
            return [{"title": "A"}]

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
    with pytest.raises(ResearchCancelled):
        DuckDuckGoBackend().search_with_cancellation(
            "agent", config=Configuration(enable_notes=False), loop_count=0,
            stop_event=stop,
        )
    assert len(calls) == (0 if cancel_at == "before" else 1)
