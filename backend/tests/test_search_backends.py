from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from config import Configuration, SearchAPI
from services.search_backends import (
    DuckDuckGoBackend,
    FallbackSearchBackend,
    SearchOutcome,
    create_search_backend,
)


def test_create_search_backend_returns_named_adapters() -> None:
    assert create_search_backend("duckduckgo").name == "duckduckgo"
    assert create_search_backend("tavily").name == "tavily"
    assert create_search_backend("searxng").name == "searxng"
    assert create_search_backend("perplexity").name == "perplexity"


def test_fallback_search_backend_switches_when_primary_raises(monkeypatch) -> None:
    config = Configuration(
        search_api=SearchAPI.TAVILY,
        search_fallback_chain=[SearchAPI.DUCKDUCKGO],
        enable_notes=False,
    )
    calls: list[str] = []

    class FailingTavily:
        name = "tavily"

        def search(self, query: str, *, config: Configuration, loop_count: int) -> SearchOutcome:
            del query, config, loop_count
            raise RuntimeError("tavily down")

    class WorkingDuckDuckGo:
        name = "duckduckgo"

        def search(self, query: str, *, config: Configuration, loop_count: int) -> SearchOutcome:
            del query, config, loop_count
            return SearchOutcome(
                payload={"results": [{"title": "A", "url": "https://example.com"}]},
                notices=[],
                answer_text=None,
                backend_label="duckduckgo",
            )

    def fake_create(backend_name: str):
        calls.append(backend_name)
        if backend_name == "tavily":
            return FailingTavily()
        return WorkingDuckDuckGo()

    monkeypatch.setattr("services.search_backends.create_search_backend", fake_create)

    outcome = FallbackSearchBackend(config).search("agent research", config=config, loop_count=0)

    assert calls == ["tavily", "duckduckgo"]
    assert outcome.backend_label == "duckduckgo"
    assert outcome.payload["results"]
    assert any("已切换" in notice for notice in outcome.notices)


def test_duckduckgo_backend_returns_normalized_outcome(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.search_backends._ddgs_search",
        lambda query, max_results=5, *, timeout_seconds=45, stop_event=None: {
            "results": [{"title": "A", "url": "https://example.com", "content": "body"}],
            "backend": "duckduckgo",
            "answer": None,
            "notices": [],
        },
    )

    outcome = DuckDuckGoBackend().search(
        "agent",
        config=Configuration(enable_notes=False),
        loop_count=0,
    )

    assert outcome.backend_label == "duckduckgo"
    assert len(outcome.payload["results"]) == 1


@pytest.mark.parametrize(
    ("budget", "steps", "expected_timeouts", "has_results", "exhausted"),
    [
        (2, [("error", 0.75), ("error", 1.25)], [2, 1.25], False, True),
        (2, [("empty", 0.25), ("success", 0.25)], [2, 1.75], True, False),
        (60, [("error", 5), ("success", 5)], [15, 15], True, False),
        (1, [("error", 0.75), ("success", 0.1)], [1, 0.25], True, False),
    ],
    ids=["budget-exhausted", "empty-then-success", "per-request-cap", "fractional-budget"],
)
def test_duckduckgo_shares_budget_across_attempts(
    monkeypatch, budget, steps, expected_timeouts, has_results, exhausted
) -> None:
    now = [0.0]
    timeouts: list[float] = []
    attempts: list[str] = []
    exits: list[object] = []

    class FakeDDGS:
        def __init__(self, *, timeout):
            timeouts.append(timeout)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            exits.append(exc_type)

        def text(self, query, *, max_results, backend):
            attempts.append(backend)
            action, duration = steps[len(attempts) - 1]
            now[0] += duration
            if action == "error":
                raise TimeoutError("request timeout")
            if action == "empty":
                return []
            return [{"title": "A", "href": "https://example.com", "body": "body"}]

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
    monkeypatch.setattr("services.search_backends.monotonic", lambda: now[0], raising=False)

    outcome = DuckDuckGoBackend().search(
        "agent", config=Configuration(search_timeout_seconds=budget), loop_count=0
    )

    assert timeouts == pytest.approx(expected_timeouts)
    assert attempts == ["lite", "api"]
    assert len(exits) == len(attempts)
    assert bool(outcome.payload["results"]) is has_results
    assert any("预算耗尽" in notice for notice in outcome.notices) is exhausted
