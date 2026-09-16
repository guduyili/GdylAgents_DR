from __future__ import annotations

from threading import Lock

import pytest

from config import Configuration, SearchAPI
from models import SummaryState, TodoItem
from services.research_pipeline import ResearchPipelineConfig
from services.skill_loader import SkillLoader
from services.task_executor import TaskExecutor


class StreamSummarizer:
    def stream_task_summary(self, state: SummaryState, task: TodoItem, context: str):
        def chunks():
            yield "Planning / retrieval / evidence / verification — 2026."

        return chunks(), lambda: "Planning / retrieval / evidence / verification — 2026."


@pytest.mark.parametrize(
    ("source_text", "expected_passed"),
    [("Planning retrieval evidence verification", True), ("Coastal tides change daily.", False)],
    ids=["supported-source", "unrelated-source"],
)
def test_execute_stream_emits_skill_loaded_and_fact_check_events(
    tmp_path, source_text: str, expected_passed: bool
) -> None:
    skill_dir = tmp_path / "deep-research"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# Deep Research\n\n## Description\n\nGuide deep research tasks.\n",
        encoding="utf-8",
    )

    state = SummaryState(research_topic="AI Agent")
    task = TodoItem(id=1, title="深度研究", intent="deep research", query="AI agent")

    executor = TaskExecutor(
        config=Configuration(
            search_api=SearchAPI.DUCKDUCKGO,
            enable_notes=False,
            enable_fact_check=True,
            skills_workspace=str(skill_dir),
            research_pipeline="plan,search,summarize,fact_check,report",
        ),
        summarizer=StreamSummarizer(),
        state_lock=Lock(),
        drain_tool_events=lambda state, step=None: [],
        search_dispatcher=lambda query, config, loop_count: (
            {
                "results": [
                    {
                        "title": "AI Agent 架构",
                        "url": "https://example.com/agent",
                        "content": "agent architecture evolution",
                    }
                ]
            },
            [],
            None,
            "duckduckgo",
        ),
        context_preparer=lambda search_result, answer_text, config: (
            f"https://example.com/article\n{source_text}",
            source_text,
        ),
        skill_loader=SkillLoader(skill_dir),
        pipeline_config=ResearchPipelineConfig.from_csv(
            "plan,search,summarize,fact_check,report"
        ),
    )

    events = list(executor.execute(state, task, emit_stream=True, step=1))
    event_types = [event["type"] for event in events]

    assert "skill_loaded" in event_types
    assert "fact_check_result" in event_types
    assert event_types.index("fact_check_result") < event_types.index("task_status")
    fact_check = next(event for event in events if event["type"] == "fact_check_result")
    assert fact_check["passed"] is expected_passed
    assert fact_check["warnings"] == []
    assert fact_check["missing_terms"] == (
        [] if expected_passed else ["Planning", "retrieval", "evidence", "verification"]
    )
    assert task.status == "completed"  # A negative check remains advisory.
