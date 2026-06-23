from __future__ import annotations

from pathlib import Path

from services.skill_loader import SkillLoader


def test_skill_loader_discovers_and_loads_matching_skill(tmp_path: Path) -> None:
    skill_dir = tmp_path / "deep-research"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# Deep Research\n\n## Description\n\nGuide deep research tasks.\n\n## Steps\n\nDo research.",
        encoding="utf-8",
    )

    loader = SkillLoader(skill_dir)
    descriptors = loader.list_skills()

    assert len(descriptors) == 1
    assert descriptors[0].name == "Deep Research"

    addon, loaded = loader.build_context_addon(
        title="深度研究",
        intent="deep research plan",
        query="AI agent",
    )

    assert loaded
    assert "Skill" in addon
    assert loaded[0].preview