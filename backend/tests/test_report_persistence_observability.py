from __future__ import annotations

from pathlib import Path

from models import SummaryState
from services.report_persistence import ReportPersistence
from tests.test_report_persistence import FakeNoteTool, FakeTracker


def test_persist_final_report_writes_run_id_metadata_to_note_payload(tmp_path: Path) -> None:
    note_tool = FakeNoteTool(["✅ 创建成功\nID: report_001"])
    persistence = ReportPersistence(
        note_tool=note_tool,
        notes_workspace=str(tmp_path),
        tool_tracker=FakeTracker(),
    )
    state = SummaryState(research_topic="AI Agent", run_id="run-meta-001")

    event = persistence.persist_final_report(state, "# 最终报告")

    assert note_tool.calls[0]["metadata"] == {"run_id": "run-meta-001"}
    assert event is not None
    assert event["run_id"] == "run-meta-001"
