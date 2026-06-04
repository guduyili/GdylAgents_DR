"""工具注册工厂：根据配置创建 NoteTool 和 ToolRegistry。"""

from __future__ import annotations

from dataclasses import dataclass

from hello_agents.tools import ToolRegistry
from hello_agents.tools.builtin.note_tool import NoteTool

from config import Configuration


@dataclass(frozen=True)
class Tooling:
    """Agent 工具基础设施。"""

    note_tool: NoteTool | None
    tools_registry: ToolRegistry | None


def create_tooling(config: Configuration) -> Tooling:
    """根据配置创建笔记工具和工具注册表。"""
    if not config.enable_notes:
        return Tooling(note_tool=None, tools_registry=None)

    note_tool = NoteTool(config.notes_workspace)
    registry = ToolRegistry()
    registry.register_tool(note_tool)
    return Tooling(note_tool=note_tool, tools_registry=registry)
