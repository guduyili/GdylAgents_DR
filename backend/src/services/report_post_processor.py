"""Report post-processing: lightweight cleanup and metadata before delivery."""

from __future__ import annotations

import re
from dataclasses import dataclass

_REFERENCE_MARKERS = ("## 参考", "## References", "## 来源", "### 来源", "参考来源")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class ReportPostProcessResult:
    """Output of report post-processing."""

    report: str
    word_count: int
    deduplicated_headings: int
    added_reference_notice: bool
    warnings: list[str]


class ReportPostProcessor:
    """Clean report headings and ensure basic reference coverage metadata."""

    def __init__(self, *, min_report_chars: int = 300) -> None:
        self._min_report_chars = min_report_chars

    def process(self, report: str, *, sources_gathered: list[str] | None = None) -> ReportPostProcessResult:
        normalized = report.strip()
        warnings: list[str] = []
        deduplicated = 0
        added_reference_notice = False

        cleaned, removed = self._dedupe_consecutive_headings(normalized)
        deduplicated = removed

        if len(cleaned) < self._min_report_chars:
            warnings.append(f"报告长度偏短（{len(cleaned)} 字）")

        has_reference = any(marker in cleaned for marker in _REFERENCE_MARKERS)
        if sources_gathered and not has_reference:
            cleaned = f"{cleaned}\n\n## 参考\n\n" + "\n".join(f"- {item}" for item in sources_gathered[:8])
            added_reference_notice = True

        return ReportPostProcessResult(
            report=cleaned,
            word_count=len(cleaned),
            deduplicated_headings=deduplicated,
            added_reference_notice=added_reference_notice,
            warnings=warnings,
        )

    @staticmethod
    def _dedupe_consecutive_headings(report: str) -> tuple[str, int]:
        lines = report.splitlines()
        output: list[str] = []
        previous_heading: str | None = None
        removed = 0

        for line in lines:
            match = _HEADING_RE.match(line.strip())
            if match:
                heading_text = match.group(2).strip()
                if heading_text == previous_heading:
                    removed += 1
                    continue
                previous_heading = heading_text
            output.append(line)

        return "\n".join(output).strip(), removed