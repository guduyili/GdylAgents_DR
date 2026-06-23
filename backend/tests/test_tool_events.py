from __future__ import annotations

from models import SummaryState
from services.tool_events import ToolCallTracker


def test_build_payload_includes_input_and_output_previews() -> None:
    tracker = ToolCallTracker(notes_workspace=None)
    tracker.record(
        {
            "agent_name": "研究规划专家",
            "tool_name": "note",
            "raw_parameters": '{"action":"create"}',
            "parsed_parameters": {"action": "create", "content": "x" * 300},
            "result": "✅ 笔记创建成功\n" + ("y" * 300),
        }
    )

    payloads = tracker.drain(SummaryState(research_topic="AI Agent"), step=1)
    assert len(payloads) == 1
    payload = payloads[0]

    assert payload["type"] == "tool_call"
    assert payload["input_preview"].endswith("…")
    assert len(payload["input_preview"]) == 201
    assert payload["output_preview"].endswith("…")
    assert payload["parameters"]["action"] == "create"
    assert "笔记创建成功" in payload["result"]