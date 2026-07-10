"""核心协调器：DeepResearchAgent 是深度研究流程的薄门面。"""

from __future__ import annotations

from threading import Event
from typing import Any, Iterator

from config import Configuration
from models import SummaryStateOutput, TodoItem
from services.research_services_factory import ResearchServices, create_research_services


class DeepResearchAgent:
    """基于 TODO 任务列表驱动的深度研究协调器薄门面。

    具体职责已经下沉到 services：
    - plan_runner：仅规划任务
    - sync_runner：同步研究流程
    - stream_runner：SSE 流式研究流程
    - research_services_factory：依赖装配
    """

    def __init__(
        self,
        config: Configuration | None = None,
        *,
        services: ResearchServices | None = None,
    ) -> None:
        """初始化协调器：只负责获取已装配好的服务集合。"""
        self.services = services or create_research_services(config or Configuration.from_env())

    @property
    def config(self) -> Configuration:
        return self.services.config

    @property
    def llm(self) -> Any:
        return self.services.llm

    @property
    def note_tool(self) -> Any:
        return self.services.note_tool

    @property
    def tools_registry(self) -> Any:
        return self.services.tools_registry

    @property
    def _tool_call_events(self) -> list[dict[str, Any]]:
        """暴露所有工具调用记录（供旧版接口兼容）。"""
        return self.services.tool_event_bridge.as_dicts()

    def plan(self, topic: str) -> list[TodoItem]:
        """仅生成研究任务规划，不执行搜索和总结。"""
        return self.services.plan_runner.plan(topic)

    def run(self, topic: str, todo_items: list[TodoItem] | None = None) -> SummaryStateOutput:
        """同步执行完整研究流程，返回最终报告。"""
        return self.services.sync_runner.run(topic, todo_items=todo_items)

    def run_stream(
        self,
        topic: str,
        todo_items: list[TodoItem] | None = None,
        *,
        stop_event: Event | None = None,
        run_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """流式执行研究流程，通过 SSE 逐步推送进度事件。"""
        yield from self.services.stream_runner.run(
            topic,
            todo_items=todo_items,
            stop_event=stop_event,
            run_id=run_id,
        )


def run_deep_research(topic: str, config: Configuration | None = None) -> SummaryStateOutput:
    """便捷函数：一行代码启动完整研究流程。"""
    agent = DeepResearchAgent(config=config)
    return agent.run(topic)
