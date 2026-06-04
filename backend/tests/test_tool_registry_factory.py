from __future__ import annotations

from hello_agents.tools import ToolRegistry
from hello_agents.tools.builtin.note_tool import NoteTool

from config import Configuration
from services.tool_registry_factory import Tooling, create_tooling


def test_create_tooling_returns_no_tools_when_notes_disabled(tmp_path) -> None:
    config = Configuration(enable_notes=False, notes_workspace=str(tmp_path))

    tooling = create_tooling(config)

    assert tooling == Tooling(note_tool=None, tools_registry=None)


def test_create_tooling_creates_note_tool_and_registry_when_notes_enabled(tmp_path) -> None:
    config = Configuration(enable_notes=True, notes_workspace=str(tmp_path))

    tooling = create_tooling(config)

    assert isinstance(tooling.note_tool, NoteTool)
    assert isinstance(tooling.tools_registry, ToolRegistry)
