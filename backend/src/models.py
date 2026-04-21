
import operator
from dataclasses import dataclass,field
from typing import List,Optional

from typing_extensions import Annotated

@dataclass(kw_only=True)
class TodoItem:
    """ 单个待办研究任务"""
    id: int                                              # 任务编号，从 1 开始
    title: str                                           # 任务标题，简短描述研究方向
    intent: str                                          # 任务意图，说明要解决的核心问题
    query: str                                           # 用于网络搜索的检索关键词
    status: str = field(default="pending")               # 任务状态：pending / in_progress / completed / skipped
    summary: Optional[str] = field(default=None)         # 任务执行完毕后的总结内容
    sources_summary: Optional[str] = field(default=None) # 搜索来源的文本摘要
    notices: list[str] = field(default_factory=list)     # 执行过程中产生的提示或警告
    note_id: Optional[str] = field(default=None)         # 关联的笔记 ID
    note_path: Optional[str] = field(default=None)       # 笔记文件的本地路径
    stream_token: Optional[str] = field(default=None)    # 流式推送时用于标识该任务的 token


@dataclass(kw_only=True)
class SummaryState:
    """ 贯穿整个研究流程的全局会话状态"""

    research_topic: str = field(default=None)            # 用户输入的研究主题
    search_query: str = field(default=None)              # 已废弃，保留作向后兼容占位符
    web_research_results: Annotated[list, operator.add] = field(default_factory=list) # 所有任务搜集到的原始搜索内容
    sources_gathered: Annotated[list, operator.add] = field(default_factory=list)     # 每个任务的来源摘要列表
    research_loop_count: int = field(default=0)          # 已完成的搜索循环次数
    running_summary: str = field(default=None)           # 兼容旧版的运行时摘要字段
    todo_items: Annotated[list, operator.add] = field(default_factory=list)           # 当前会话的待办任务列表
    structured_report: Optional[str] = field(default=None)      # 最终生成的结构化报告
    report_note_id: Optional[str] = field(default=None)         # 报告笔记的 ID
    report_note_path: Optional[str] = field(default=None)       # 报告笔记的本地路径


@dataclass(kw_only=True)
class SummaryStateInput:
    """ 研究流程的输入参数"""
    research_topic: str = field(default=None)           # 用户提交的研究主题

@dataclass(kw_only=True)
class SummaryStateOutput:
    """ 研究流程的当前状态"""

    running_summary: str = field(default=None)              # 向后兼容的文本摘要
    report_markdown: Optional[str] = field(default=None)    # Markdown 格式的最终报告
    todo_items: List[TodoItem] = field(default_factory=list)    # 所有任务极其执行结果