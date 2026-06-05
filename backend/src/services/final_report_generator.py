"""最终报告生成器：统一处理报告生成和失败兜底。"""

from __future__ import annotations

import logging
from typing import Protocol

from models import SummaryState

logger = logging.getLogger(__name__)


class ReportingLike(Protocol):
    def generate_report(self, state: SummaryState) -> str: ...


class FinalReportGenerator:
    """调用 ReportingService，并在失败时用任务摘要生成兜底报告。"""

    def __init__(self, *, reporting: ReportingLike) -> None:
        self._reporting = reporting

    def generate(self, state: SummaryState) -> str:
        return self.generate_report(state)

    def generate_report(self, state: SummaryState) -> str:
        try:
            return self._reporting.generate_report(state)
        except Exception as exc:
            logger.exception("报告生成失败，使用任务摘要兜底: %s", exc)
            summaries = "\n\n".join(
                f"### {task.title}\n{task.summary or '暂无摘要'}"
                for task in state.todo_items
            )
            return f"## 研究摘要（报告生成失败，使用任务摘要兜底）\n\n{summaries}"
