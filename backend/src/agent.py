"""核心协调器：DeepResearchAgent 负责串联规划→搜索→总结→报告的完整研究流程。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Any, Callable, Iterator

from hello_agents import ToolAwareSimpleAgent
from hello_agents.tools import ToolRegistry
from hello_agents.tools.builtin.note_tool import NoteTool

from config import Configuration
from prompts import (
    report_writer_instructions,
    task_summarizer_instructions,
    todo_planner_system_prompt,
)
from models import SummaryState, SummaryStateOutput, TodoItem
from services.llm_factory import create_llm
from services.planner import PlanningService
from services.reporter import ReportingService
from services.search import dispatch_search, prepare_research_context
from services.summarizer import SummarizationService
from services.tool_events import ToolCallTracker




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
        self.note_tool = (
            NoteTool(self.config.notes_workspace)
            if self.config.enable_notes
            else None
        )

        self.tools_registry: ToolRegistry | None = None
        if self.note_tool:
            registry = ToolRegistry()
            registry.register_tool(self.note_tool)
            self.tools_registry = registry

        # 工具调用事件追踪器：用于收集 Agent 的工具调用记录并推送给前端
        self._tool_tracker = ToolCallTracker(
            self.config.notes_workspace if self.config.enable_notes else None
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
            self._execute_task(state,task,emit_stream=False)

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
        """流式执行研究流程，通过 SSE 逐步推送进度事件。
        
        事件类型（type 字段）：
        - status：流程状态提示
        - todo_list：规划完成，返回任务列表
        - task_status：单个任务状态变更
        - sources：任务搜索到的来源
        - task_summary_chunk：任务总结的流式文本块
        - final_report：最终报告
        - done：流程结束
        """
        state = SummaryState(research_topic=topic)
        logger.debug("开始流式研究： topic=%s",topic)
        yield {"type": "status", "message": "初始化研究流程"}
        
        # 规划任务；如果调用方已传入任务清单，则直接执行确认后的规划。
        if todo_items is not None:
            state.todo_items = todo_items
        else:
            state.todo_items = self.planner.plan_todo_list(state)
            for event in self._drain_tool_events(state, step=0):
                yield event
        if not state.todo_items:
            state.todo_items = [self.planner.create_fallback_task(state=state)]
        
        # 为每个任务分配步骤编号和流标识（前端用于区分不同任务的输出流）
        channel_map: dict[int,dict[str, Any]] = {}
        for index,task in enumerate(state.todo_items, start=1):
            token = f"task_{task.id}"
            task.stream_token = token
            channel_map[task.id] = {"step":index, "token":token}
        
        yield {
            "type":"todo_list",
            "tasks":[self._serialize_task(t) for t in state.todo_items],
            "step":0,
        }
        
        # 使用队列在多线程任务和主线程推送之间传递事件
        event_queue: Queue[dict[str, Any]] = Queue()

        def enqueue(
            event: dict[str, Any],
            *,
            task: TodoItem | None = None,
            step_override: int | None = None,
        ) -> None:
            """将事件加入队列，自动附加任务 ID 和流标识。"""
            payload = dict(event)
            target_task_id = payload.get("task_id")
            if task is not None:
                target_task_id = task.id
                payload["task_id"] = task.id    
            
            channel = channel_map.get(target_task_id) if target_task_id is not None else None
            if channel:
                payload.setdefault("step", channel["step"])
                payload["stream_token"] = channel["token"]
            if step_override is not None:
                payload["step"] = step_override
            
            event_queue.put(payload)

        def tool_event_sink(event:  dict[str,Any]) -> None:
            """工具调用事件实时回调：直接入队推送给前端。"""
            enqueue(event)


        self._set_tool_event_sink(tool_event_sink)

        threads: list[Thread] = []

        def worker(task: TodoItem, step: int)->None:
            """
            每个任务在独立线程中执行，完成后发送内部任务完成信号。
            """
            try:
                enqueue(
                    {
                        "type": "task_status",
                        "task_id": task.id,
                        "status": "in_progress",
                        "title": task.title,
                        "intent": task.intent,
                        "note_id": task.note_id,
                        "note_path": task.note_path,
                    },
                    task=task,
                )
                for event in self._execute_task(state,task,emit_stream=True,step=step):
                    enqueue(event, task=task)


            except Exception as exc:
                logger.exception("任务执行失败",exc_info=exc)
                enqueue(
                    {
                        "type":"task_status",
                        "task_id": task.id,
                        "status": "failed",
                        "error": str(exc),
                        "title":task.title,
                        "intent": task.intent,
                        "note_id": task.note_id,
                        "note_path": task.note_path,
                    },
                    task=task,
                )
            finally:
                enqueue({"type":"__task_done__","task_id":task.id})

        # 启动所有任务线程（并发执行）
        for task in state.todo_items:
            step = channel_map.get(task.id,{}).get("step",0)
            thread = Thread(target=worker, args=(task, step), daemon=True)
            threads.append(thread)
            thread.start()
        active_workers = len(state.todo_items)
        finished_workers = 0

        # 主线程从队列消费事件，推送给前端，直到所有任务完成
        try:
            while finished_workers < active_workers:
                event = event_queue.get()
                if event.get("type") == "__task_done__":
                    finished_workers += 1
                    continue
                yield event

        # 消费队列中剩余的非终止事件
        finally:
            self._set_tool_event_sink(None)
            for thread in threads:
                thread.join()

        # 所有任务完成后生成最终报告
        final_step = len(state.todo_items) + 1
        try:
            report = self.reporting.generate_report(state)
        except Exception as exc:
            logger.exception("报告生成失败，将使用任务摘要兜底: %s", exc)
            summaries = "\n\n".join(
                f"### {t.title}\n{t.summary or '暂无摘要'}"
                for t in state.todo_items
            )
            report = f"## 研究摘要（报告生成失败，使用任务摘要兜底）\n\n{summaries}"

        for event in self._drain_tool_events(state, step=final_step):
            yield event
        state.structured_report = report
        state.running_summary = report

        note_event = self._persist_final_report(state, report)
        if note_event:
            yield note_event

        yield {
            "type": "final_report",
            "report": report,
            "note_id": state.report_note_id,
            "note_path": state.report_note_path,
        }

        yield {"type": "done"}


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
        task.status = "in_progress"

        # 搜索阶段
        search_result,notices,answer_text,backend = dispatch_search(
            task.query,
            self.config,
            state.research_loop_count
        )
        self._last_search_notices = notices
        task.notices = notices

        if emit_stream:
            for event in self._drain_tool_events(state, step=step):
                yield event
        else:
            self._drain_tool_events(state)


        # 推送搜索提示（如有）
        if notices and emit_stream:
            for notice in notices:
                if notice:
                    yield{
                        "type":"status",
                        "message": notice,
                        "task_id": task.id,
                        "step": step,
                    }

        # 如果搜索无结果，跳过该任务
        if not search_result or not search_result.get("results"):
            task.status = "skipped"
            if emit_stream:
                for event in self._drain_tool_events(state, step=step):
                    yield event
                yield {
                    "type": "task_status",
                    "task_id": task.id,
                    "status": "skipped",
                    "title": task.title,
                    "intent": task.intent,
                    "note_id": task.note_id,
                    "note_path": task.note_path,
                    "step": step,
                }
            else:
                self._drain_tool_events(state)
            return
        else:
            if not emit_stream:
                self._drain_tool_events(state)
        
        # 准备供LLM使用的研究上下文
        sources_summary, context = prepare_research_context(
            search_result,
            answer_text,
            self.config,
        )
        task.sources_summary = sources_summary

        # 加锁更新共享状态（多线程安全）
        with self._state_lock:
            state.web_research_results.append(context),
            state.sources_gathered.append(sources_summary)
            state.research_loop_count += 1
        summary_text: str| None = None

        if emit_stream:
            for event in self._drain_tool_events(state, step=step):
                yield event
            yield{
                "type":"sources",
                "task_id": task.id,
                "latest_sources": sources_summary,
                "raw_context": context,
                "step": step,
                "backend": backend,
                "note_id": task.note_id,
                "note_path": task.note_path,
            }

            # 流式总结： 逐 chunk 推送给前端
            summary_steam, summary_getter = self.summarizer.stream_task_summary(state,task,context)
            try:
                for event in self._drain_tool_events(state, step=step):
                    yield event
                for chunk in summary_steam:
                    if chunk:
                        yield{
                            "type":"task_summary_chunk",
                            "task_id": task.id,
                            "content": chunk,
                            "note_id": task.note_id,
                            "step": step,
                        }
                    for event in self._drain_tool_events(state,step = step):
                        yield event
            finally:
                summary_text = summary_getter()
        else:
            # 同步总结
            summary_text = self.summarizer.summarize_task(state, task, context)
            self._drain_tool_events(state)
        
        task.summary = summary_text.strip() if summary_text else "暂无可用信息"
        task.status = "completed"

        if emit_stream:
            for event in self._drain_tool_events(state, step=step):
                yield event
            yield{
                "type":"task_status",
                "task_id": task.id,
                "status": "completed",
                "summary": task.summary,
                "sources_summary": task.sources_summary,
                "note_id": task.note_id,
                "note_path": task.note_path,
                "step": step,
            }
        else:
            self._drain_tool_events(state)


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
        if not self.note_tool or not report or not report.strip():
            return None

        note_title = f"研究报告：{state.research_topic}".strip() or "研究报告"
        tags = ["deep_research", "report"]
        content = report.strip()

        note_id = self._find_existing_note_id(state)
        response=""

        if note_id:
            # 已有报告笔记，执行更新
            response = self.note_tool.run(
                {
                    "action": "update",
                    "note_id": note_id,
                    "title": note_title,
                    "note_type": "conclusion",
                    "tags": tags,
                    "content": content,
                }
            )
            if response.startswith("❌"):
                note_id = None  # 更新失败，降级为新建
        if not note_id:
            # 新建报告笔记
            response = self.note_tool.run(
                {
                    "action": "create",
                    "title": note_title,
                    "note_type": "conclusion",
                    "tags": tags,
                    "content": content,
                }
            )
            note_id = self._extract_note_id_from_text(response)

        if not note_id:
            return None

        state.report_note_id = note_id
        if self.config.notes_workspace:
            note_path = Path(self.config.notes_workspace) / f"{note_id}.md"
            state.report_note_path = str(note_path)
        else:
            note_path = None

        payload = {
            "type": "report_note",
            "note_id": note_id,
            "title": note_title,
            "content": content,
        }
        if note_path:
            payload["note_path"] = str(note_path)

        return payload


    def _find_existing_note_id(self,state: SummaryState)->str | None:
        """
        查找已存在的报告笔记 ID 避免重复创建
        """
        if state.report_note_id:
            return state.report_note_id

        # 从工具调用历史中反向查找最终报告类型的笔记
        for event in reversed(self._tool_tracker.as_dicts()):
            if event.get("tool") != "note":
                continue
            parameters = event.get("parsed_parameters") or {}
            if not isinstance(parameters, dict):
                continue

            action = parameters.get("action")
            if action != "create":
                continue

            note_type = parameters.get("note_type")
            if note_type != "conclusion":
                title = parameters.get("title")
                if not (isinstance(title,str) and title.startswith("研究报告：")):
                    continue

            note_id = parameters.get("note_id")
            if not note_id:
                note_id = self._tool_tracker._extract_note_id(event.get("result", ""))
            
            if note_id:
             return note_id
        return None

    @staticmethod
    def _extract_note_id_from_text(response: str) -> str | None:
        """从笔记工具的返回文本中提取 note_id。"""
        if not response:
            return None

        match = re.search(r"ID:\s*([^\n]+)", response)
        if not match:
            return None

        return match.group(1).strip()



def run_deep_research(topic: str, config: Configuration | None = None)->SummaryState:
    """便捷函数：一行代码启动完整研究流程。"""
    agent = DeepResearchAgent(config = config)
    return agent.run(topic)
    
        
    
    
        
