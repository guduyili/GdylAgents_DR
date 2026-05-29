"""Report persistence helpers for local note-backed research reports."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class UnsafeReportIdError(ValueError):
    """Raised when a report id contains unsafe characters or traversal."""


class ReportNotFoundError(FileNotFoundError):
    """Raised when the requested report markdown file does not exist."""


class ReportStore:
    """Read conclusion reports from the local notes workspace."""

    _SAFE_NOTE_ID = re.compile(r"^[a-zA-Z0-9_\-]+$")

    def __init__(self, note_dir: str | Path) -> None:
        self.note_dir = Path(note_dir).resolve()

    def list_reports(self) -> list[dict[str, Any]]:
        """Return conclusion notes from notes_index.json sorted newest first."""
        index_path = self.note_dir / "notes_index.json"
        if not index_path.exists():
            return []

        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        notes = data.get("notes", [])
        reports = [
            {
                "id": note["id"],
                "title": note.get("title", ""),
                "created_at": note.get("created_at", ""),
                "tags": note.get("tags", []),
            }
            for note in notes
            if isinstance(note, dict) and note.get("type") == "conclusion" and note.get("id")
        ]
        return sorted(reports, key=lambda item: item["created_at"], reverse=True)

    def get_report(self, note_id: str) -> dict[str, str]:
        """Return one report by note id after validating path safety."""
        note_path = self._resolve_note_path(note_id)
        if not note_path.exists():
            raise ReportNotFoundError(note_id)

        content = note_path.read_text(encoding="utf-8")
        title, body = self._split_frontmatter(content, fallback_title=note_id)
        return {"id": note_id, "title": title, "content": body}

    def _resolve_note_path(self, note_id: str) -> Path:
        """Validate a note id and return the resolved markdown file path."""
        if not self._SAFE_NOTE_ID.match(note_id):
            raise UnsafeReportIdError(note_id)

        note_path = (self.note_dir / f"{note_id}.md").resolve()
        if not note_path.is_relative_to(self.note_dir):
            raise UnsafeReportIdError(note_id)
        return note_path

    @staticmethod
    def _split_frontmatter(content: str, *, fallback_title: str) -> tuple[str, str]:
        """Extract a simple YAML frontmatter title and markdown body."""
        title = fallback_title
        body = content
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                frontmatter = content[3:end].strip()
                body = content[end + 3 :].strip()
                for line in frontmatter.splitlines():
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip().strip('"').strip("'")
                        break
        return title, body
