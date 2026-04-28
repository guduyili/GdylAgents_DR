"""报告服务：将所有任务总结汇总，生成最终的结构化研究报告。"""

from __future__ import annotations


import json

from hello_agents import ToolAwareSimpleAgent

from models import SummaryState
from config import Configuration
from utils import strip_thinking_tokens
from services.text_processing import strip_tool_calls



class ReportingService:
    """调用报告 Agent,根据所有任务结果生成最终 Markdown 报告。"""

    def __init__(self,report_agent: ToolAwareSimpleAgent, config: Configuration) -> None:
        self._agent = report_agent   # 负责撰写报告的 LLM Agent
        self._config = config        # 全局配置
    
    def generate_report(self, state: SummaryState)->str:
        """根据已完成的任务总结生成结构化研究报告。
        
        Args:
            state: 包含所有任务结果的研究状态。
        
        Returns:
            清理后的 Markdown 格式报告文本。
        """
        # 将每个任务的信息拼成文本块
        tasks_block = []
        for task in state.todo_items:
            summary_task = task.summary or "暂无可用信息"
            sources_block = task.sources_summary or "暂无来源"
            tasks_block.append(
                f"### 任务{task.id}: {task.title}\n"
                f"- 任务目标{task.intent}\n"
                f"- 检索查询{task.query}\n"
                f"- 执行状态{task.status}\n"
                f"- 任务总结{summary_task}\n"
                f"- 来源概括{sources_block}\n"
            )

        # 收集所有任务关联的笔记 ID， 供Agent读取
        note_references =[]
        for task in state.todo_items:
            if task.note_id:
                note_references.append(
                    f"- 任务{task.id}《{task.title}》：note_id={task.note_id}"
                )

        notes_section = "\n".join(note_references) if note_references else "- 暂无可用任务笔记"

        #构建笔记读取和结论创建的 TOOL_CALL 模版(提示 Agent如何操作笔记)
        read_template = json.dumps({"action": "read","note_id": "<note_id>"}, ensure_ascii=False)
        create_conclusion_template = json.dumps(
            {
                "action": "create",
                "title": f"研究报告:{state.research_topic}",
                "note_type": "conclusion",
                "tags": ["deep_research","report"],
                "content": "请在此沉淀最终报告要点",
            },
            ensure_ascii = False,
        )

        # 拼装发给报告 Agent的完整的 prompt
        prompt = {
            f"研究主题：{state.research_topic}\n"
            f"任务概览：\n{''.join(tasks_block)}\n"
            f"可用任务笔记：\n{notes_section}\n"
            f"请针对每条任务笔记使用格式：[TOOL_CALL:note:{read_template}] 读取内容，整合所有信息后撰写报告。\n"
            f"如需输出汇总结论，可追加调用：[TOOL_CALL:note:{create_conclusion_template}] 保存报告要点。"
        }
        
        response = self._agent.run(prompt)
        self._agent.clear_history() # 清空对话历史，避免污染后续调用

        report_text = response.strip()
        if self._config.strip_thinking_tokens:
            report_text = strip_thinking_tokens(report_text)

        report_text = strip_tool_calls(report_text).strip()
        return report_text or "报告生成失败，请检查输入"
        
