"""Configuration environment parsing tests."""

from __future__ import annotations

import os

from config import Configuration, SearchAPI


def test_search_fallback_chain_parses_csv_env(monkeypatch):
    monkeypatch.setenv("SEARCH_FALLBACK_CHAIN", "duckduckgo,tavily")

    config = Configuration.from_env()

    assert config.search_fallback_chain == [SearchAPI.DUCKDUCKGO, SearchAPI.TAVILY]


def test_search_fallback_chain_field_env_parses_csv(monkeypatch):
    monkeypatch.delenv("SEARCH_FALLBACK_CHAIN", raising=False)
    monkeypatch.setenv("SEARCH_FALLBACK_CHAIN", "duckduckgo, tavily")

    config = Configuration.from_env()

    assert config.search_fallback_chain == [SearchAPI.DUCKDUCKGO, SearchAPI.TAVILY]