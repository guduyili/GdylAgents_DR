"""研究服务装配工厂：集中创建 DeepResearchAgent 需要的全部服务。"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

from hello_agents.tools import ToolRegistry
from hello_agents.tools.builtin.note_tool import NoteTool

from config import Configuration
from services.agent_factory import AgentFactory
from services.final_report_generator import FinalReportGenerator
from services.llm_factory import create_llm
from services.plan_runner import PlanRunner
from services.planner import PlanningService
from services.report_persistence import ReportPersistence
from services.reporter import ReportingService
from services.research_run_store import InMemoryResearchRunStore, ResearchRunStore, SQLiteResearchRunStore
from services.stream_runner import StreamRunner
from services.summarizer import SummarizationService
from services.sync_runner import SyncRunner
from services.task_executor import TaskExecutor
from services.task_serializer import serialize_task
from services.tool_event_bridge import ToolEventBridge
from services.tool_events import ToolCallTracker
from services.tool_registry_factory import create_tooling


@dataclass
class ResearchServices:
    """DeepResearchAgent 的依赖集合。"""

    config: Configuration
    llm: Any
    note_tool: NoteTool | None
    tools_registry: ToolRegistry | None
    tool_tracker: ToolCallTracker
    tool_event_bridge: ToolEventBridge
    report_persistence: ReportPersistence
    agent_factory: AgentFactory
    todo_agent: Any
    report_agent: Any
    summarizer_factory: Any
    planner: PlanningService
    plan_runner: PlanRunner
    summarizer: SummarizationService
    reporting: ReportingService
    final_report_generator: FinalReportGenerator
    task_executor: TaskExecutor
    sync_runner: SyncRunner
    stream_runner: StreamRunner
    run_store: ResearchRunStore


def create_research_services(
    config: Configuration,
    *,
    run_store: ResearchRunStore | None = None,
) -> ResearchServices:
    """按固定依赖顺序装配完整研究服务。"""
    llm = create_llm(config)
    if run_store is None:
        if config.run_store_backend == "sqlite":
            run_store = SQLiteResearchRunStore(config.run_store_db_path)
        else:
            run_store = InMemoryResearchRunStore()
    tooling = create_tooling(config)
    tool_tracker = ToolCallTracker(config.notes_workspace if config.enable_notes else None)
    tool_event_bridge = ToolEventBridge(tracker=tool_tracker)
    report_persistence = ReportPersistence(
        note_tool=tooling.note_tool,
        notes_workspace=config.notes_workspace if config.enable_notes else None,
        tool_tracker=tool_tracker,
    )

    agent_factory = AgentFactory(
        config=config,
        default_llm=llm,
        tools_registry=tooling.tools_registry,
        tool_call_listener=tool_tracker.record,
    )
    todo_agent = agent_factory.create_todo_agent()
    report_agent = agent_factory.create_report_agent()
    summarizer_factory = agent_factory.create_summarizer_factory()

    planner = PlanningService(todo_agent, config)
    plan_runner = PlanRunner(
        planner=planner,
        drain_tool_events=tool_event_bridge.drain,
    )
    summarizer = SummarizationService(summarizer_factory, config=config)
    reporting = ReportingService(report_agent, config)
    final_report_generator = FinalReportGenerator(reporting=reporting)
    state_lock = Lock()
    task_executor = TaskExecutor(
        config=config,
        summarizer=summarizer,
        state_lock=state_lock,
        drain_tool_events=tool_event_bridge.drain,
    )
    sync_runner = SyncRunner(
        planner=planner,
        task_executor=task_executor,
        final_report_generator=final_report_generator,
        drain_tool_events=tool_event_bridge.drain,
        persist_final_report=report_persistence.persist_final_report,
    )
    stream_runner = StreamRunner(
        planner=planner,
        task_executor=task_executor,
        reporting=final_report_generator,
        drain_tool_events=tool_event_bridge.drain,
        set_tool_event_sink=tool_event_bridge.set_sink,
        persist_final_report=report_persistence.persist_final_report,
        serialize_task=serialize_task,
        run_store=run_store,
    )

    return ResearchServices(
        config=config,
        llm=llm,
        note_tool=tooling.note_tool,
        tools_registry=tooling.tools_registry,
        tool_tracker=tool_tracker,
        tool_event_bridge=tool_event_bridge,
        report_persistence=report_persistence,
        agent_factory=agent_factory,
        todo_agent=todo_agent,
        report_agent=report_agent,
        summarizer_factory=summarizer_factory,
        planner=planner,
        plan_runner=plan_runner,
        summarizer=summarizer,
        reporting=reporting,
        final_report_generator=final_report_generator,
        task_executor=task_executor,
        sync_runner=sync_runner,
        stream_runner=stream_runner,
        run_store=run_store,
    )
