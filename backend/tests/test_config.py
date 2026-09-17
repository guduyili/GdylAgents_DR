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


def test_decision_execution_limits_parse_from_environment(monkeypatch):
    monkeypatch.setenv("TASK_EXECUTION_MODE", "decision")
    monkeypatch.setenv("DECISION_MAX_STEPS", "6")
    monkeypatch.setenv("DECISION_TOTAL_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("DECISION_TIMEOUT_SECONDS", "9")

    config = Configuration.from_env()

    assert config.task_execution_mode == "decision"
    assert config.decision_max_steps == 6
    assert config.decision_total_timeout_seconds == 45
    assert config.decision_timeout_seconds == 9
