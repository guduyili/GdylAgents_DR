from __future__ import annotations

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
        lambda query, max_results=5: {
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