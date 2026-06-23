"""Research pipeline configuration and stage wiring."""

from __future__ import annotations

from dataclasses import dataclass

from services.agent_registry import AgentRegistry


DEFAULT_PIPELINE_STAGES = ("plan", "search", "summarize", "fact_check", "report", "review")


@dataclass(frozen=True)
class ResearchPipelineConfig:
    """Declarative stage list for the research workflow."""

    stages: tuple[str, ...] = DEFAULT_PIPELINE_STAGES

    def is_enabled(self, stage: str) -> bool:
        return stage in self.stages

    @classmethod
    def from_csv(cls, raw: str | None) -> "ResearchPipelineConfig":
        if not raw:
            return cls()
        stages = tuple(item.strip() for item in raw.split(",") if item.strip())
        return cls(stages=stages or DEFAULT_PIPELINE_STAGES)


@dataclass(frozen=True)
class ResearchPipeline:
    """Resolved pipeline agents created from a registry."""

    config: ResearchPipelineConfig
    planner_agent: object
    summarizer_agent_factory: object
    reporter_agent: object

    @classmethod
    def from_registry(
        cls,
        registry: AgentRegistry,
        *,
        config: ResearchPipelineConfig | None = None,
        summarizer_factory: object | None = None,
    ) -> "ResearchPipeline":
        pipeline_config = config or ResearchPipelineConfig()
        return cls(
            config=pipeline_config,
            planner_agent=registry.create("planner"),
            summarizer_agent_factory=summarizer_factory,
            reporter_agent=registry.create("reporter"),
        )