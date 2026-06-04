"""核心协调器：DeepResearchAgent 负责串联规划→搜索→总结→报告的完整研究流程。"""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any, Callable, Iterator

from hello_agents import ToolAwareSimpleAgent

from config import Configuration
from prompts import (
    report_writer_instructions,
    task_summarizer_instructions,
    todo_planner_system_prompt,
)
from models import SummaryState, SummaryStateOutput, TodoItem
from services.llm_factory import create_llm
from services.planner import PlanningService
from services.report_persistence import ReportPersistence
from services.reporter import ReportingService
from services.summarizer import SummarizationService
from services.task_executor import TaskExecutor
from services.stream_runner import StreamRunner
from services.tool_events import ToolCallTracker
from services.tool_registry_factory import create_tooling




logger = logging.getLogger(__name__)


class DeepResearchAgent:
    """基于 TODO 任务列表驱动的深度研究协调器。
    
    工作流程：
    1. 规划（planner）：将用户主题拆解为 3~5 个子任务
    2. 执行（单任务）：搜索 → 总结
    3. 报告（reporter）：汇总所有任务结果，生成最终报告
    """

    def __init__(self, config: Configuration | None = None) -> None:
        """
        初始化协调器：加载配置、创建 LLM、初始化笔记和各服务。
        """
        self.config = config or Configuration.from_env()
        self.llm = create_llm(self.config)              # 根据配置创建 HelloAgentsLLM 实例
        
        # 如果启用笔记功能，初始化 NoteTool 和工具注册表
        tooling = create_tooling(self.config)
        self.note_tool = tooling.note_tool
        self.tools_registry = tooling.tools_registry

        # 工具调用事件追踪器：用于收集 Agent 的工具调用记录并推送给前端
        self._tool_tracker = ToolCallTracker(
            self.config.notes_workspace if self.config.enable_notes else None
        )
        self.report_persistence = ReportPersistence(
            note_tool=self.note_tool,
            notes_workspace=self.config.notes_workspace if self.config.enable_notes else None,
            tool_tracker=self._tool_tracker,
        )

        self._tool_event_sink_enabled = False
        self._state_lock = Lock()       # 多线程执行任务时保护共享状态

        # 创建三种角色的 Agent 实例
        self.todo_agent = self._create_tool_aware_agent(
            name="研究规划专家",
            system_prompt=todo_planner_system_prompt.strip(),
        )
        self.report_agent = self._create_tool_aware_agent(
            name="报告撰写专家",
            system_prompt=report_writer_instructions.strip(),
            model_override=self.config.resolved_report_model(),
        )
        # 总结 Agent 使用工厂函数，每个任务创建独立实例，避免历史污染
        self._summarizer_factory : Callable[[],ToolAwareSimpleAgent] = lambda: self._create_tool_aware_agent(
            name="任务总结专家",
            system_prompt=task_summarizer_instructions.strip(),
        )

        # 三个业务服务
        self.planner = PlanningService(
            self.todo_agent,self.config
        )

        self.summarizer = SummarizationService(
            self._summarizer_factory,
            config=self.config,
        )

        self.reporting = ReportingService(
            self.report_agent,
            self.config,
        )
        self.task_executor = TaskExecutor(
            config=self.config,
            summarizer=self.summarizer,
            state_lock=self._state_lock,
            drain_tool_events=self._drain_tool_events,
        )
        self.stream_runner = StreamRunner(
            planner=self.planner,
            task_executor=self.task_executor,
            reporting=self.reporting,
            drain_tool_events=self._drain_tool_events,
            set_tool_event_sink=self._set_tool_event_sink,
            persist_final_report=self._persist_final_report,
            serialize_task=self._serialize_task,
        )
        self._last_search_notices: list[str] = []


    def _create_tool_aware_agent(self, *, name: str, system_prompt: str, model_override: str | None = None) -> ToolAwareSimpleAgent:
        """
        创建共享LLM和工具注册表的ToolAwareSimpleAgent 实例。
        model_override 不为空时，为该 agent 单独创建一个指定模型的 LLM 实例。
        """
        if model_override and model_override != self.config.resolved_model():
            # 用相同连接参数，只换 model 名称
            llm = create_llm(self.config, model_override=model_override)
        else:
            llm = self.llm
        return ToolAwareSimpleAgent(
            name=name,
            llm=llm,
            system_prompt=system_prompt,
            enable_tool_calling=self.tools_registry is not None,
            tool_registry=self.tools_registry,
            tool_call_listener=self._tool_tracker.record,
        )

    def _set_tool_event_sink(self, sink: Callable[[dict[str,Any]], None]| None)->None:
        """启用或禁用工具事件的实时回调（流式模式下使用）。"""
        self._tool_event_sink_enabled = sink is not None
        self._tool_tracker.set_event_sink(sink)

    def plan(self, topic: str) -> list[TodoItem]:
        """仅生成研究任务规划，不执行搜索和总结。"""
        state = SummaryState(research_topic=topic)
        todo_items = self.planner.plan_todo_list(state)
        self._drain_tool_events(state)
        if not todo_items:
            todo_items = [self.planner.create_fallback_task(state)]
        return todo_items

    def run(self, topic:str, todo_items: list[TodoItem] | None = None)-> SummaryStateOutput:
        """同步执行完整研究流程，返回最终报告。
        
        适合一次性获取完整结果的场景（非流式）。
        """
        state = SummaryState(research_topic=topic)
        # 第一步： 规划任务列表
        if todo_items is not None:
            state.todo_items = todo_items
        else:
            state.todo_items = self.planner.plan_todo_list(state)
            self._drain_tool_events(state)

        
        if not state.todo_items:
            logger.info("规划未产生任务，使用兜底任务")
            state.todo_items = [self.planner.create_fallback_task(state)]

        
        # 第二步： 逐个执行任务（搜索 + 总结）
        for task in state.todo_items:
            for _event in self._execute_task(state, task, emit_stream=False):
                # 同步模式不向调用方返回中间事件，但必须消耗生成器以真正执行任务。
                pass

        # 第三步： 生成最终报告
        try:
            report = self.reporting.generate_report(state)
        except Exception as exc:
            logger.exception("报告生成失败，使用任务摘要兜底: %s", exc)
            summaries = "\n\n".join(
                f"### {t.title}\n{t.summary or '暂无摘要'}"
                for t in state.todo_items
            )
            report = f"## 研究摘要（报告生成失败，使用任务摘要兜底）\n\n{summaries}"
        self._drain_tool_events(state)
        state.structured_report = report
        state.running_summary = report
        self._persist_final_report(state, report)

        return SummaryStateOutput(
            running_summary=report,
            report_markdown=report,
            todo_items=state.todo_items,
        )

    def run_stream(self, topic: str, todo_items: list[TodoItem] | None = None)-> Iterator[dict[str,Any]]:
        """流式执行研究流程，通过 SSE 逐步推送进度事件。"""
        yield from self.stream_runner.run(topic, todo_items=todo_items)


    # ------------------------------------------------------------------
    # 任务执行辅助方法
    # ------------------------------------------------------------------
    def _execute_task(
        self,
        state: SummaryState,
        task: TodoItem,
        *,
        emit_stream: bool,
        step: int | None = None,
    
    )-> Iterator[dict[str,Any]]:
        """执行单个任务：搜索 → 准备上下文 → 总结。"""
        events = self.task_executor.execute(
            state,
            task,
            emit_stream=emit_stream,
            step=step,
        )
        yield from events
        self._last_search_notices = self.task_executor.last_search_notices


    def _drain_tool_events(
        self,
        state: SummaryState,
        *,
        step: int| None = None)->list[dict[str,Any]]:
        """从工具追踪器中提取尚未消费的事件。
        
        流式模式下事件由事件接收器实时推送，此方法返回空列表；
        同步模式下此方法负责推送积压的事件。
        """
        events = self._tool_tracker.drain(state,step=step)
        if self._tool_event_sink_enabled:
            return []
        return  events

    @property
    def _tool_call_events(self)->list[dict[str,Any]]:
        """
        暴露所有工具调用记录（供旧版接口兼容）
        """
        return self._tool_tracker.as_dicts()

    def _serialize_task(self, task: TodoItem) -> dict[str, Any]:
        """将 TodoItem 转为可序列化的字典（供前端 JSON 使用）。"""
        return {
            "id": task.id,
            "title": task.title,
            "intent": task.intent,
            "status": task.status,
            "summary": task.summary,
            "sources_summary": task.sources_summary,
            "notices": task.notices,
            "note_id": task.note_id,
            "note_path": task.note_path,
            "stream_token": task.stream_token,
        }

    

    def _persist_final_report(self, state: SummaryState, report: str) -> dict[str, Any] | None:
        """将最终报告写入笔记并返回笔记事件（供前端展示）。"""
        return self.report_persistence.persist_final_report(state, report)



def run_deep_research(topic: str, config: Configuration | None = None)->SummaryState:
    """便捷函数：一行代码启动完整研究流程。"""
    agent = DeepResearchAgent(config = config)
    return agent.run(topic)
    
        
    
    
        
