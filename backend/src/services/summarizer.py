"""总结服务：对单个任务的搜索结果调用 LLM 生成摘要。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Tuple

from hello_agents import ToolAwareSimpleAgent

from models import SummaryState, TodoItem
from config import Configuration
from utils import strip_thinking_tokens
from services.notes import build_note_guidance
from services.text_processing import strip_tool_calls



class SummarizationService:
    """ 提供同步和流式两种任务的总结方式"""

    def __init__(
        self,
        summarizer_factory: Callable[[], ToolAwareSimpleAgent],
        config: Configuration,
    )->None:
    # 工厂函数： 每次需要总结时创建一个新的 Agent实例， 避免对话历史污染
        self._agent_factory = summarizer_factory
        self._config = config


    def summarize_task(self, state: SummaryState, task: TodoItem, context: str)->str:
        """同步模式：调用总结 Agent，返回完整的任务摘要文本。
        
        Args:
            state: 全局研究状态（用于获取主题信息）。
            task: 当前待总结的任务。
            context: 该任务搜索到的原始内容（已格式化）。
        
        Returns:
            清理后的 Markdown 摘要文本。
        """
        prompt = self._build_prompt(state,task,context)
        agent = self._agent_factory()
        try:
            response = agent.run(prompt)
        finally:
            agent.clear_history() # 无论是否异常，都清空历史
        
        summary_text = response.strip()
        if self._config.strip_thinking_tokens:
            summary_text = strip_thinking_tokens(summary_text)


        summary_text = strip_tool_calls(summary_text).strip()
        return summary_text or "暂无可用信息"

    def stream_task_summary(
        self, state: SummaryState, task: TodoItem, context:str
    )->Tuple[Iterator[str], Callable[[],str]]:
        """流式模式：边生成边 yield 文本块，同时收集完整输出。
        
        返回一个生成器和一个 getter 函数：
        - 生成器：迭代时逐块 yield 给前端（自动过滤 <think> 片段）
        - getter：流结束后调用，获取完整的清理后文本
        
        Args:
            state: 全局研究状态。
            task: 当前任务。
            context: 搜索上下文。
        
        Returns:
            (chunk_generator, get_full_summary) 二元组
        """

        prompt = self._build_prompt(state,task,context)
        remove_thinking = self._config.strip_thinking_tokens
        raw_buffer = ""         #原始 chunk 累积缓冲区
        visible_output = ""     #去除 <think>后到可见输出
        emit_index = 0          #已向外推送到的位置（用于跳过<think>区间）
        agent = self._agent_factory()

        def flush_visible()->Iterator[str]:
            """ 从raw_buffer中提取<think>标签之外的可见文本块"""
            nonlocal emit_index,raw_buffer
            while True:
                start = raw_buffer.find("<think>",emit_index)
                if start == -1:
                    # 没有<think>,直接推送剩余部分
                    if emit_index < len(raw_buffer):
                        segment = raw_buffer[emit_index:]
                        emit_index = len(raw_buffer)
                        if segment:
                            yield segment
                    break
                
                # 推送<think>之前的文本
                if start > emit_index:
                    segment = raw_buffer[emit_index:start]
                    emit_index = start
                    if segment:
                        yield segment


                # 等待</think>出现再跳过整个思考块
                end = raw_buffer.find("</think>",start)
                if end == -1:
                    break # </think> 还没到达，等待下一个 chunk
                emit_index = end + len("</think>")
                            
        def generator()->Iterator[str]:
            """流式 chunk 生成器，过滤思考标签后向外 yield。"""
            nonlocal raw_buffer,visible_output,emit_index
            try:
                for chunk in agent.stream_run(prompt):
                    raw_buffer += chunk
                    if remove_thinking:
                        for segment in flush_visible():
                            yield segment
                    else:
                        visible_output += chunk
                        if chunk:
                            yield chunk

            finally:
                # 流结束后，确保<think>之后点剩余可见文本被推送出去
                if remove_thinking:
                    for segment in flush_visible():
                        visible_output += segment
                        if segment:
                            yield segment
                agent.clear_history()

        def get_summary()->str:
            """流结束后获取完整的清理后摘要文本。"""
            if remove_thinking:
                cleaned = strip_thinking_tokens(visible_output)
            else:
                cleaned = visible_output
            return strip_tool_calls(cleaned).strip()
        return generator(), get_summary

    def _build_prompt(self, state: SummaryState, task: TodoItem, context: str) -> str:
            """拼装发给总结 Agent 的 prompt。
        
            包含：研究主题、任务信息、搜索上下文、笔记协作指引。
            """
            return (
            f"任务主题：{state.research_topic}\n"
            f"任务名称：{task.title}\n"
            f"任务目标：{task.intent}\n"
            f"检索查询：{task.query}\n"
            f"任务上下文：\n{context}\n"
            f"{build_note_guidance(task)}\n"
            "请按照以上协作要求先同步笔记，然后返回一份面向用户的 Markdown 总结（仍遵循任务总结模板）。"
        )


            


