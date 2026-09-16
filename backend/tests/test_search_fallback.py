from __future__ import annotations

import pytest

from config import Configuration, SearchAPI
from services.search import dispatch_search
from services.search_backends import SearchOutcome


def test_dispatch_search_falls_back_when_primary_raises(monkeypatch) -> None:
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

    payload, notices, _answer, backend = dispatch_search("agent research", config, 0)

    assert calls == ["tavily", "duckduckgo"]
    assert backend == "duckduckgo"
    assert payload["results"]
    assert any("已切换" in notice for notice in notices)


def test_dispatch_search_returns_empty_when_all_backends_fail(monkeypatch) -> None:
    config = Configuration(
        search_api=SearchAPI.TAVILY,
        search_fallback_chain=[SearchAPI.DUCKDUCKGO],
        enable_notes=False,
    )

    class AlwaysFail:
        def __init__(self, name: str) -> None:
            self.name = name

        def search(self, query: str, *, config: Configuration, loop_count: int) -> SearchOutcome:
            del query, config, loop_count
            raise RuntimeError(f"{self.name} down")

    monkeypatch.setattr(
        "services.search_backends.create_search_backend",
        lambda backend_name: AlwaysFail(backend_name),
    )

    payload, notices, answer, backend = dispatch_search("agent research", config, 0)

    assert backend == "tavily"
    assert payload["results"] == []
    assert answer is None
    assert len(notices) >= 2


@pytest.mark.parametrize(
    ("durations", "successful_backend", "expected_calls", "exhausted"),
    [
        ([2, 0, 0], "duckduckgo", ["tavily"], True),
        ([3, 0, 0], "duckduckgo", ["tavily"], True),
        ([0.5, 0.5, 0], "duckduckgo", ["tavily", "duckduckgo"], False),
        ([0.75, 1.25, 0], "searxng", ["tavily", "duckduckgo"], True),
    ],
    ids=["exact-deadline", "over-deadline", "fallback-within-budget", "shared-chain-budget"],
)
def test_dispatch_search_stops_fallback_after_budget_exhaustion(
    monkeypatch, durations, successful_backend, expected_calls, exhausted
) -> None:
    config = Configuration(
        search_api=SearchAPI.TAVILY,
        search_fallback_chain=[SearchAPI.DUCKDUCKGO, SearchAPI("searxng")],
        search_timeout_seconds=2,
        enable_notes=False,
    )
    original_config = config.model_dump()
    now = [0.0]
    created: list[str] = []
    calls: list[str] = []

    class TimedBackend:
        def __init__(self, name):
            self.name = name

        def search(self, query, *, config, loop_count):
            calls.append(self.name)
            now[0] += durations[len(calls) - 1]
            if self.name != successful_backend:
                raise RuntimeError(f"{self.name} down")
            return SearchOutcome(
                payload={"results": [{"title": "A", "url": "https://example.com"}]},
                notices=[], answer_text=None, backend_label=self.name,
            )

    def create_backend(name):
        created.append(name)
        return TimedBackend(name)

    monkeypatch.setattr("services.search_backends.monotonic", lambda: now[0])
    monkeypatch.setattr("services.search_backends.create_search_backend", create_backend)

    payload, notices, answer, backend = dispatch_search("agent", config, 0)

    assert calls == expected_calls
    assert created == expected_calls
    assert any("预算耗尽" in notice for notice in notices) is exhausted
    assert any("tavily down" in notice for notice in notices)
    assert bool(payload["results"]) is not exhausted
    assert backend == ("tavily" if exhausted else "duckduckgo")
    assert answer is None
    assert config.model_dump() == original_config
