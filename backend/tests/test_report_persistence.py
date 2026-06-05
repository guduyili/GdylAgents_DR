from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from models import SummaryState
from services.report_persistence import ReportPersistence, extract_note_id_from_text


class FakeNoteTool:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def run(self, payload: dict) -> str:
        self.calls.append(payload)
        if not self.responses:
            return ""
        return self.responses.pop(0)


class FakeTracker:
    def __init__(self, events: list[dict] | None = None) -> None:
        self._events = events or []

    def as_dicts(self) -> list[dict]:
        return self._events


@dataclass
class FakeConfig:
    notes_workspace: str


def test_extract_note_id_from_text_reads_id_line() -> None:
    assert extract_note_id_from_text("✅ 创建成功\nID: note_123\n路径: x") == "note_123"


def test_persist_final_report_creates_report_note_and_updates_state(tmp_path: Path) -> None:
    note_tool = FakeNoteTool(["✅ 创建成功\nID: report_001"])
    persistence = ReportPersistence(
        note_tool=note_tool,
        notes_workspace=str(tmp_path),
        tool_tracker=FakeTracker(),
    )
    state = SummaryState(research_topic="AI Agent")

    event = persistence.persist_final_report(state, "# 最终报告")

    assert note_tool.calls == [
        {
            "action": "create",
            "title": "研究报告：AI Agent",
            "note_type": "conclusion",
            "tags": ["deep_research", "report"],
            "content": "# 最终报告",
            "metadata": {},
    }]
    assert state.report_note_id == "report_001"
    assert state.report_note_path == str(tmp_path / "report_001.md")
    assert event == {
        "type": "report_note",
        "note_id": "report_001",
        "title": "研究报告：AI Agent",
        "content": "# 最终报告",
        "note_path": str(tmp_path / "report_001.md"),
    }


def test_persist_final_report_updates_existing_note_from_state(tmp_path: Path) -> None:
    note_tool = FakeNoteTool(["✅ 更新成功\nID: existing_001"])
    persistence = ReportPersistence(
        note_tool=note_tool,
        notes_workspace=str(tmp_path),
        tool_tracker=FakeTracker(),
    )
    state = SummaryState(research_topic="FastAPI SSE", report_note_id="existing_001")

    event = persistence.persist_final_report(state, "  ## 新报告  ")

    assert note_tool.calls[0]["action"] == "update"
    assert note_tool.calls[0]["note_id"] == "existing_001"
    assert note_tool.calls[0]["content"] == "## 新报告"
    assert event is not None
    assert event["note_id"] == "existing_001"


def test_persist_final_report_falls_back_to_create_when_update_fails(tmp_path: Path) -> None:
    note_tool = FakeNoteTool(["❌ 更新失败", "✅ 创建成功\nID: replacement_001"])
    persistence = ReportPersistence(
        note_tool=note_tool,
        notes_workspace=str(tmp_path),
        tool_tracker=FakeTracker(),
    )
    state = SummaryState(research_topic="Fallback", report_note_id="old_001")

    event = persistence.persist_final_report(state, "fallback report")

    assert [call["action"] for call in note_tool.calls] == ["update", "create"]
    assert state.report_note_id == "replacement_001"
    assert event is not None
    assert event["note_id"] == "replacement_001"


def test_persist_final_report_reuses_existing_report_note_from_tool_history(tmp_path: Path) -> None:
    note_tool = FakeNoteTool(["✅ 更新成功"])
    tracker = FakeTracker(
        [
            {
                "tool": "note",
                "parsed_parameters": {
                    "action": "create",
                    "note_type": "conclusion",
                    "title": "研究报告：历史主题",
                },
                "result": "✅ 创建成功\nID: history_001",
            }
        ]
    )
    persistence = ReportPersistence(
        note_tool=note_tool,
        notes_workspace=str(tmp_path),
        tool_tracker=tracker,
    )
    state = SummaryState(research_topic="历史主题")

    event = persistence.persist_final_report(state, "history report")

    assert note_tool.calls[0]["action"] == "update"
    assert note_tool.calls[0]["note_id"] == "history_001"
    assert event is not None
    assert event["note_id"] == "history_001"


def test_persist_final_report_returns_none_without_note_tool(tmp_path: Path) -> None:
    persistence = ReportPersistence(
        note_tool=None,
        notes_workspace=str(tmp_path),
        tool_tracker=FakeTracker(),
    )
    state = SummaryState(research_topic="No notes")

    assert persistence.persist_final_report(state, "report") is None
    assert state.report_note_id is None


def test_persist_final_report_returns_none_for_blank_report(tmp_path: Path) -> None:
    note_tool = FakeNoteTool([])
    persistence = ReportPersistence(
        note_tool=note_tool,
        notes_workspace=str(tmp_path),
        tool_tracker=FakeTracker(),
    )

    assert persistence.persist_final_report(SummaryState(research_topic="Blank"), "  ") is None
    assert note_tool.calls == []
