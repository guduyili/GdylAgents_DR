from __future__ import annotations

from services.report_post_processor import ReportPostProcessor


def test_report_post_processor_dedupes_headings_and_adds_reference_section() -> None:
    report = "# 报告\n\n# 报告\n\n正文内容。" * 40

    result = ReportPostProcessor(min_report_chars=100).process(
        report,
        sources_gathered=["来源 A", "来源 B"],
    )

    assert result.deduplicated_headings >= 1
    assert "## 参考" in result.report
    assert result.added_reference_notice is True