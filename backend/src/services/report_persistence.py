"""Persist generated research reports through the HelloAgents NoteTool."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol

from models import SummaryState


class NoteToolLike(Protocol):
    """Minimal NoteTool protocol used by report persistence."""

    def run(self, payload: dict[str, Any]) -> str:
        """Execute a note action and return the tool response text."""


class ToolTrackerLike(Protocol):
    """Minimal tool tracker protocol used to inspect note tool history."""

    def as_dicts(self) -> list[dict[str, Any]]:
        """Return tracked tool call events as dictionaries."""


def extract_note_id_from_text(response: str) -> str | None:
    """Extract a note id from NoteTool response text."""
    if not response:
        return None

    match = re.search(r"ID:\s*([^\n]+)", response)
    if not match:
        return None

    return match.group(1).strip()


class ReportPersistence:
    """Write final reports to NoteTool-backed local notes."""

    def __init__(
        self,
        *,
        note_tool: NoteToolLike | None,
        notes_workspace: str | None,
        tool_tracker: ToolTrackerLike,
    ) -> None:
        self.note_tool = note_tool
        self.notes_workspace = notes_workspace
        self.tool_tracker = tool_tracker

    def persist_final_report(self, state: SummaryState, report: str) -> dict[str, Any] | None:
        """Persist the final report and return a frontend report_note event."""
        if not self.note_tool or not report or not report.strip():
            return None

        note_title = f"研究报告：{state.research_topic}".strip() or "研究报告"
        tags = ["deep_research", "report"]
        content = report.strip()

        note_id = self.find_existing_note_id(state)

        if note_id:
            response = self.note_tool.run(
                {
                    "action": "update",
                    "note_id": note_id,
                    "title": note_title,
                    "note_type": "conclusion",
                    "tags": tags,
                    "content": content,
                }
            )
            if response.startswith("❌"):
                note_id = None

        if not note_id:
            response = self.note_tool.run(
                {
                    "action": "create",
                    "title": note_title,
                    "note_type": "conclusion",
                    "tags": tags,
                    "content": content,
                }
            )
            note_id = extract_note_id_from_text(response)

        if not note_id:
            return None

        state.report_note_id = note_id
        note_path: Path | None
        if self.notes_workspace:
            note_path = Path(self.notes_workspace) / f"{note_id}.md"
            state.report_note_path = str(note_path)
        else:
            note_path = None

        payload: dict[str, Any] = {
            "type": "report_note",
            "note_id": note_id,
            "title": note_title,
            "content": content,
        }
        if note_path:
            payload["note_path"] = str(note_path)

        return payload

    def find_existing_note_id(self, state: SummaryState) -> str | None:
        """Find an existing report note id from state or tracked note tool calls."""
        if state.report_note_id:
            return state.report_note_id

        for event in reversed(self.tool_tracker.as_dicts()):
            if event.get("tool") != "note":
                continue

            parameters = event.get("parsed_parameters") or {}
            if not isinstance(parameters, dict):
                continue

            if parameters.get("action") != "create":
                continue

            note_type = parameters.get("note_type")
            if note_type != "conclusion":
                title = parameters.get("title")
                if not (isinstance(title, str) and title.startswith("研究报告：")):
                    continue

            note_id = parameters.get("note_id")
            if not note_id:
                note_id = extract_note_id_from_text(str(event.get("result", "")))

            if note_id:
                return str(note_id)

        return None
