"""
工具调用事件追踪器: 收集Agent的工具调用记录,供日志记录和前端SSE推送使用
"""
from __future__ import annotations
import re

import logging

from dataclasses import dataclass

from pathlib import Path
from threading import Lock
from typing import Any, Callable, Optional


from models import SummaryState, TodoItem

logger = logging.getLogger(__name__)

@dataclass
class ToolCallEvent:
    """单次工具调用的内部数据结构。"""

    id: int                              # 事件序号（从1开始）
    agent: str                           # 发起调用的 Agent 名称
    tool: str                            # 被调用的工具名
    raw_parameters: str                  # 原始参数字符串（用于调试）
    parsed_parameters: dict[str, Any]    # 解析后的参数字典
    result: str                          # 工具返回的结果文本
    task_id: Optional[int]               # 关联的任务 ID（可能无法推断）
    note_id: Optional[str]               # 关联的笔记 ID（仅 note 工具有）


class ToolCallTracker:
    """收集工具调用事件，并将其转换为 SSE 推送载荷。
    
    线程安全：内部使用 Lock，可在多任务并发场景下安全使用。
    工作模式：
    - 同步模式：事件积累在内部队列，由 drain() 批量提取
    - 流式模式：注册 event_sink 后，每次调用立即触发回调推送给前端
    """
    def __init__(self, notes_workspace: Optional[str]) -> None:
        self._notes_workspace = notes_workspace         # 笔记存储目录，用于拼接note_path
        self._events: list[ToolCallEvent] = []                                  # 用于记录所有已记录的事件列表
        self._cursor = 0                                                        # 已被 drain() 的事件数
        self._lock = Lock()                                 # 保护_events 和 _cursor 的并发访问
        self._event_sink: Optional[Callable[[dict[str,Any]],None]] = None       # 实时推送回调
    
    def record(self, payload: dict[str,Any])->None:
        """记录一次工具调用事件。
        
        由 ToolAwareSimpleAgent 的 tool_call_listener 回调触发。
        如果已注册 event_sink，会立即推送给前端（流式模式）。
        """
        agent_name = str(payload.get("agent_name") or "unknown")
        tool_name = str(payload.get("tool_name") or "unknown")
        raw_parameters = str(payload.get("raw_parameters") or "")
        parsed_parameters = payload.get("parsed_parameters") or {}
        result_text = str(payload.get("result") or "")

        # 确保 parsed_parameters 是字典，避免后续 .get() 报错
        if not isinstance(parsed_parameters, dict):
            parsed_parameters = {}

        # 从参数中推断关联的任务ID
        task_id = self._infer_task_id(parsed_parameters)
        note_id: Optional[str] = None

        # 对note工具，优先从参数中取 note_id 否则从返回结果中提取
        if tool_name == "note":
            note_id = parsed_parameters.get("note_id")
            if note_id is None:
                note_id = self._extract_note_id(result_text)
        
        event = ToolCallEvent(
            id = len(self._events) +1,
            agent=agent_name,
            tool=tool_name,
            raw_parameters=raw_parameters,
            parsed_parameters=parsed_parameters,
            result=result_text,
            task_id=task_id,
            note_id=note_id,
        )

        with self._lock:
            self._events.append(event)


        logger.info(
            "工具调用已记录: agent=%s tool=%s task_id=%s note_id=%s parsed_parameters=%s",
            agent_name,
            tool_name,
            task_id,
            note_id,
            parsed_parameters,
        )

        # 流式模式： 立即通过 sink推送事件
        sink = self._event_sink
        if sink:
            sink(self._build_payload(event, step=None))
    

    # ------------------------------------------------------------------
    # 事件提取方法
    # ------------------------------------------------------------------
    def drain(self, state: SummaryState, *, step: Optional[int] = None)->list[dict[str,Any]]:
        """提取自上次 drain 以来尚未消费的新事件。
        
        同时将事件中的 note_id 同步回对应任务的 note_id/note_path 字段。
        流式模式下事件已由 sink 实时推送，此方法返回空列表。
        """
        with self._lock:
            if self._cursor >= len(self._events):
                return []
            #  截取新增事件并推送游标
            new_events = self._events[self._cursor:]
            self._cursor = len(self._events)

        # 将 note_id 同步到对应 TodoItem 方便前端展示笔记链接
        if state.todo_items:
            for event in new_events:
                task_id = event.task_id
                note_id = event.note_id
                if task_id is None or not note_id:
                    continue
                self._attach_note_to_task(state.todo_items, task_id,note_id)


        # 将每个事件转换为可JSON序列化的字典
        payloads: list[dict[str, Any]] = []
        for event in new_events:
            payload = self._build_payload(event, step=step)
            payloads.append(payload)
            
        return payloads

    def reset(self) ->None:
        """
        清空所有已记录事件 用于测试或重置场景
        """
        with self._lock:
            self._events.clear()
            self._cursor = 0


    def as_dicts(self)->list[dict[str, Any]]:
        """
        返回所有事件的原始字典快照 供旧版接口兼容使用
        """
        with self._lock:
            return [
                {
                    "id": event.id,
                    "agent": event.agent,
                    "tool": event.tool,
                    "raw_parameters": event.raw_parameters,
                    "parsed_parameters": event.parsed_parameters,
                    "result": event.result,
                    "task_id": event.task_id,
                    "note_id": event.note_id,
                }
                for event in self._events
            ]
            
    def set_event_sink(self, sink: Optional[Callable[[dict[str, Any]], None]])->None:
        """注册/取消工具事件的实时推送回调。
        
        sink 不为 None 时进入流式模式，每次 record() 都会立即触发回调。
        """
        self._event_sink = sink

    def _build_payload(self, event: ToolCallEvent, step: Optional[int]) -> dict[str, Any]:
        """
        将内部 ToolCallEvent 转换为可推送给前端的 SSE 载荷字典
        """
        payload = {
            "type": "tool_call",
            "event_id": event.id,
            "agent": event.agent,
            "tool": event.tool,
            "parameters": event.parsed_parameters,
            "result": event.result,
            "task_id": event.task_id,
            "note_id": event.note_id,
        }
        # 如果有笔记目录配置， 附加本地文件路径方便前端打开
        if event.note_id and self._notes_workspace:
            note_path = Path(self._notes_workspace) / f"{event.note_id}.md"
            payload["note_path"] = str(note_path)
        if step is not None:
            payload["step"] = step
        return payload
    
    # ------------------------------------------------------------------
    # 私有辅助方法
    # ------------------------------------------------------------------
    def _attach_note_to_task(self,tasks: list[TodoItem], task_id: int, note_id: str)->None:
        """
        将 note_id 和 note_path 写入对应的 TodoItem。
        """
        for task in tasks:
            if task.id != task_id:
                continue
            if task.note_id != note_id:
                task.note_id = note_id
                if self._notes_workspace:
                    task.note_path = str(Path(self._notes_workspace) / f"{note_id}.md")
            elif task.note_path is None and self._notes_workspace:
                # note_id 已存在但路径还没填入，补全路径
                task.note_path = str(Path(self._notes_workspace) / f"{note_id}.md")
            break

    def _infer_task_id(self, parameters: dict[str, Any]) -> Optional[int]:
        """从工具参数中推断关联的任务 ID。
        
        依次尝试三种来源：
        1. parameters["task_id"] 字段
        2. parameters["tags"] 列表中的 "task_N" 标签
        3. parameters["title"] 字段中的 "任务N" 中文格式
        """
        if not parameters:
            return None
        
        # 方式1：直接读取 task_id 字段
        if "task_id" in parameters:
            try:
                return int(parameters["task_id"])
            except (TypeError, ValueError):
                pass

        
        # 方式2: 从tags中匹配 task_N格式
        tags = parameters.get("tags")
        if isinstance(tags, list):
            for tag in tags:
                match = re.search(r"task_(\d+)", str(tag))
                if match:
                    return int(match.group(1))

        # 方式3: 从标题中匹配“任务N”中文格式
        title = parameters.get("title")
        if isinstance(title, str):
            match = re.search(r"任务\s*(\d+)", title)
            if match:
                return int(match.group(1))

        return None

    def _extract_note_id(self, response:str)->Optional[str]:
        """从笔记工具返回文本中提取 note_id（格式：ID: <note_id>）。"""
        if not response:
            return None
        
        match = re.search(r"ID:\s*([^\n]+)", response)
        if match:
            return match.group(1).strip()
        
        return None