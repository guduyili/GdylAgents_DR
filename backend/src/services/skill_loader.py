"""Skill loader: discover SKILL.md files and inject guidance into task context."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_DESCRIPTION_RE = re.compile(r"(?:^|\n)##\s*Description\s*\n+(.+?)(?:\n##|\Z)", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class SkillDescriptor:
    """Metadata for a discoverable skill."""

    name: str
    path: str
    description: str


@dataclass(frozen=True)
class SkillLoadResult:
    """Loaded skill content ready for prompt injection."""

    name: str
    description: str
    preview: str
    content: str


class SkillLoader:
    """Load SKILL.md instructions from a workspace directory."""

    def __init__(self, workspace: str | Path | None) -> None:
        self._workspace = Path(workspace) if workspace else None

    def list_skills(self) -> list[SkillDescriptor]:
        if self._workspace is None or not self._workspace.exists():
            return []

        descriptors: list[SkillDescriptor] = []
        for skill_file in sorted(self._workspace.rglob("SKILL.md")):
            content = skill_file.read_text(encoding="utf-8", errors="ignore")
            name = self._extract_name(content, fallback=skill_file.parent.name)
            descriptors.append(
                SkillDescriptor(
                    name=name,
                    path=str(skill_file),
                    description=self._extract_description(content),
                )
            )
        return descriptors

    def select_skills_for_task(self, *, title: str, intent: str, query: str) -> list[SkillDescriptor]:
        """Pick skills whose name/description loosely matches the task text."""
        haystack = f"{title} {intent} {query}".lower()
        selected: list[SkillDescriptor] = []
        for skill in self.list_skills():
            tokens = [skill.name.lower(), *skill.description.lower().split()]
            if any(len(token) >= 3 and token in haystack for token in tokens):
                selected.append(skill)
        return selected[:2]

    def load_skill(self, descriptor: SkillDescriptor, *, max_chars: int = 4000) -> SkillLoadResult:
        path = Path(descriptor.path)
        content = path.read_text(encoding="utf-8", errors="ignore").strip()
        if len(content) > max_chars:
            content = f"{content[:max_chars]}\n... [skill truncated]"
        preview = content[:200].replace("\n", " ").strip()
        return SkillLoadResult(
            name=descriptor.name,
            description=descriptor.description,
            preview=preview,
            content=content,
        )

    def build_context_addon(self, *, title: str, intent: str, query: str) -> tuple[str, list[SkillLoadResult]]:
        """Return concatenated skill guidance and the loaded skill payloads."""
        loaded: list[SkillLoadResult] = []
        blocks: list[str] = []
        for descriptor in self.select_skills_for_task(title=title, intent=intent, query=query):
            try:
                result = self.load_skill(descriptor)
            except OSError as exc:
                logger.warning("读取 Skill 失败 path=%s error=%s", descriptor.path, exc)
                continue
            loaded.append(result)
            blocks.append(f"### Skill: {result.name}\n{result.content}")

        if not blocks:
            return "", loaded

        return "\n\n".join(["## 已加载 Skill 指引", *blocks]), loaded

    @staticmethod
    def _extract_name(content: str, *, fallback: str) -> str:
        match = _TITLE_RE.search(content)
        if match:
            return match.group(1).strip()
        return fallback

    @staticmethod
    def _extract_description(content: str) -> str:
        match = _DESCRIPTION_RE.search(content)
        if match:
            return " ".join(match.group(1).split())[:240]
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
        return lines[0][:240] if lines else "No description"