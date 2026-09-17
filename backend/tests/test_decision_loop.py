from threading import Event

import pytest

from models import TodoItem
from services.decision_loop import DecisionLoop
from services.search_backends import SearchOutcome


def collect(generator):
    events = []
    while True:
        try:
            events.append(next(generator))
        except StopIteration as done:
            return events, done.value


def task():
    return TodoItem(id=1, title="Agent", intent="learn", query="agent")


def outcome(results=None):
    return SearchOutcome({"results": results or []}, [], None, "fake")


def test_empty_search_can_rewrite_then_finish_with_evidence():
    actions = iter([
        {"action": "search", "query": "agent", "reason": "collect"},
        {"action": "search", "query": "agent tools", "reason": "rewrite empty query"},
        {"action": "finish", "reason": "evidence collected"},
    ])
    contexts, queries = [], []

    def decide(context, remaining):
        contexts.append(context)
        return next(actions)

    def search(query, remaining):
        queries.append(query)
        return outcome([] if len(queries) == 1 else [
            {"title": "A", "url": "https://example.com", "content": "Evidence"},
        ])

    records, result = collect(DecisionLoop(max_steps=4, timeout_seconds=60).run(
        task(), "topic", decide=decide, search=search,
    ))
    assert queries == ["agent", "agent tools"]
    assert contexts[1].observations[0].result_count == 0
    assert contexts[2].observations[1].sources[0].content == "Evidence"
    assert result.stop_reason == "finish"
    assert len(result.outcome.payload["results"]) == 1
    assert records[-1]["stop_reason"] == "finish"


@pytest.mark.parametrize("action, expected", [
    ({"action": "shell", "reason": "bad"}, "invalid_action"),
    ({"action": "finish", "reason": "done"}, "no_evidence"),
])
def test_invalid_and_empty_finish_never_search(action, expected):
    calls = []
    _, result = collect(DecisionLoop(max_steps=2, timeout_seconds=60).run(
        task(), "topic", decide=lambda *args: action,
        search=lambda *args: calls.append(args),
    ))
    assert result.stop_reason == expected
    assert not calls


@pytest.mark.parametrize("repeat", [True, False])
def test_repeated_query_and_step_limit_are_bounded(repeat):
    calls = []
    def decide(context, remaining):
        return {"action": "search", "query": " AGENT  " if repeat else str(context.step), "reason": "search"}
    _, result = collect(DecisionLoop(max_steps=3, timeout_seconds=60).run(
        task(), "topic", decide=decide,
        search=lambda query, remaining: calls.append(query) or outcome(),
    ))
    assert result.stop_reason == ("repeated_query" if repeat else "step_limit")
    assert len(calls) == (1 if repeat else 3)


def test_timeout_discards_late_decision_before_search():
    now, calls = [0.0], []
    def decide(*args):
        now[0] = 5
        return {"action": "search", "query": "agent", "reason": "collect"}
    _, result = collect(DecisionLoop(max_steps=2, timeout_seconds=5, clock=lambda: now[0]).run(
        task(), "topic", decide=decide, search=lambda *args: calls.append(args),
    ))
    assert result.stop_reason == "timeout"
    assert not calls


def test_cancelled_decision_never_searches():
    from services.cancellation import ResearchCancelled
    stop, calls = Event(), []
    def decide(*args):
        stop.set()
        return {"action": "search", "query": "agent", "reason": "collect"}
    with pytest.raises(ResearchCancelled):
        collect(DecisionLoop(max_steps=2, timeout_seconds=60).run(
            task(), "topic", decide=decide, search=lambda *args: calls.append(args), stop_event=stop,
        ))
    assert not calls


def test_search_errors_are_observations_and_sources_are_deduplicated():
    def decide(context, remaining):
        if context.step == 1:
            return {"action": "search", "query": "first", "reason": "collect"}
        if context.step == 2:
            assert context.observations[0].error == "RuntimeError"
            return {"action": "search", "query": "second", "reason": "recover"}
        return {"action": "finish", "reason": "done"}
    def search(query, remaining):
        if query == "first":
            raise RuntimeError("private provider message")
        return outcome([
            {"url": "https://example.com", "title": "A", "content": "x" * 4000},
            {"url": "https://example.com", "title": "duplicate"},
            {"url": "javascript:bad", "title": "bad"},
        ])
    records, result = collect(DecisionLoop(max_steps=3, timeout_seconds=60).run(
        task(), "topic", decide=decide, search=search,
    ))
    assert len(result.outcome.payload["results"]) == 1
    assert len(result.outcome.payload["results"][0]["content"]) == 2000
    assert "private provider message" not in str(records)
