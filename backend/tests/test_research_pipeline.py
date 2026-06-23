from __future__ import annotations

from services.research_pipeline import ResearchPipelineConfig


def test_pipeline_config_from_csv_parses_stages() -> None:
    config = ResearchPipelineConfig.from_csv("plan,search,summarize,report")

    assert config.is_enabled("plan") is True
    assert config.is_enabled("fact_check") is False
    assert config.is_enabled("review") is False