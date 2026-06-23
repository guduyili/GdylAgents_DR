"""报告评审服务：对生成的研究报告做轻量规则校验。"""

from __future__ import annotations

from dataclasses import dataclass

from models import SummaryState


REFERENCE_MARKERS = (
    "## 参考",
    "## References",
    "## 来源",
    "### 来源",
    "## 参考来源",
    "参考来源",
)


@dataclass(frozen=True)
class ReviewResult:
    """规则评审的输出。"""

    passed: bool
    score: int
    issues: list[str]
    suggestions: list[str]


class ReviewService:
    """基于启发式规则审查报告完整性与来源引用。"""

    def __init__(self, *, min_report_chars: int = 500) -> None:
        self._min_report_chars = min_report_chars

    def review(self, state: SummaryState, report: str) -> ReviewResult:
        issues: list[str] = []
        suggestions: list[str] = []
        normalized = report.strip()
        char_count = len(normalized)

        if char_count < self._min_report_chars:
            issues.append(f"报告过短（{char_count} 字），建议补充摘要或参考来源")

        has_reference_section = any(marker in normalized for marker in REFERENCE_MARKERS)
        has_gathered_sources = any(
            (task.sources_summary or "").strip() for task in state.todo_items
        ) or bool(state.sources_gathered)

        if has_gathered_sources and not has_reference_section:
            suggestions.append("建议添加「参考」章节并引用搜索来源")

        if not has_gathered_sources and not has_reference_section:
            issues.append("报告缺少参考来源章节，且未关联任何搜索来源")

        completed_tasks = [task for task in state.todo_items if task.status == "completed"]
        if state.todo_items and not completed_tasks:
            issues.append("所有任务均未成功完成，报告可能缺少有效内容")

        failed_tasks = [task for task in state.todo_items if task.status == "failed"]
        if failed_tasks:
            suggestions.append(f"有 {len(failed_tasks)} 个任务执行失败，建议核对摘要完整性")

        score = max(0, 100 - len(issues) * 25 - len(suggestions) * 10)
        passed = len(issues) == 0
        return ReviewResult(
            passed=passed,
            score=score,
            issues=issues,
            suggestions=suggestions,
        )