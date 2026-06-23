from __future__ import annotations

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