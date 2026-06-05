"""Agent 创建工厂：集中管理 ToolAwareSimpleAgent 构造细节。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from hello_agents import ToolAwareSimpleAgent
from hello_agents.tools import ToolRegistry

from config import Configuration
from prompts import (
    report_writer_instructions,
    task_summarizer_instructions,
    todo_planner_system_prompt,
)
from services.llm_factory import create_llm

AgentT = TypeVar("AgentT")


class AgentFactory:
    """创建研究流程中使用的各类 ToolAwareSimpleAgent。"""

    def __init__(
        self,
        *,
        config: Configuration,
        default_llm: Any,
        tools_registry: ToolRegistry | None,
        tool_call_listener: Callable[[dict[str, Any]], None],
        llm_creator: Callable[..., Any] = create_llm,
        agent_class: type[AgentT] = ToolAwareSimpleAgent,
    ) -> None:
        self._config = config
        self._default_llm = default_llm
        self._tools_registry = tools_registry
        self._tool_call_listener = tool_call_listener
        self._llm_creator = llm_creator
        self._agent_class = agent_class

    def create_tool_aware_agent(
        self,
        *,
        name: str,
        system_prompt: str,
        model_override: str | None = None,
    ) -> AgentT:
        """创建共享默认 LLM 或指定模型 LLM 的工具感知 Agent。"""
        if model_override and model_override != self._config.resolved_model():
            llm = self._llm_creator(self._config, model_override=model_override)
        else:
            llm = self._default_llm

        return self._agent_class(
            name=name,
            llm=llm,
            system_prompt=system_prompt,
            enable_tool_calling=self._tools_registry is not None,
            tool_registry=self._tools_registry,
            tool_call_listener=self._tool_call_listener,
        )

    def create_todo_agent(self) -> AgentT:
        return self.create_tool_aware_agent(
            name="研究规划专家",
            system_prompt=todo_planner_system_prompt.strip(),
        )

    def create_report_agent(self) -> AgentT:
        return self.create_tool_aware_agent(
            name="报告撰写专家",
            system_prompt=report_writer_instructions.strip(),
            model_override=self._config.resolved_report_model(),
        )

    def create_summarizer_factory(self) -> Callable[[], AgentT]:
        return lambda: self.create_tool_aware_agent(
            name="任务总结专家",
            system_prompt=task_summarizer_instructions.strip(),
        )
