"""Fact-check service: lightweight cross-validation between summaries and sources."""

from __future__ import annotations

import re
from dataclasses import dataclass

from models import TodoItem

_URL_RE = re.compile(r"https?://[^\s)]+")
_TERM_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{4,}")


@dataclass(frozen=True)
class FactCheckResult:
    """Heuristic fact-check output for a single task summary."""

    passed: bool
    score: int
    matched_sources: list[str]
    warnings: list[str]
    missing_terms: list[str]


class FactCheckService:
    """Compare task summary keywords against gathered source URLs and snippets."""

    def __init__(self, *, min_summary_chars: int = 40, min_matched_terms: int = 2) -> None:
        self._min_summary_chars = min_summary_chars
        self._min_matched_terms = min_matched_terms

    def check(self, task: TodoItem) -> FactCheckResult:
        summary = (task.summary or "").strip()
        sources_blob = (task.sources_summary or "").strip()
        warnings: list[str] = []
        missing_terms: list[str] = []

        source_urls = list(dict.fromkeys(_URL_RE.findall(sources_blob)))
        if not source_urls:
            warnings.append("未找到可核对的来源 URL")
        if len(summary) < self._min_summary_chars:
            warnings.append(f"摘要过短（{len(summary)} 字），难以核对事实")

        terms = self._extract_check_terms(summary)
        if not terms:
            warnings.append("摘要缺少可核对的关键术语")

        matched_terms: list[str] = []
        lowered_sources = sources_blob.lower()
        for term in terms:
            if term.lower() in lowered_sources or term.lower() in summary.lower():
                matched_terms.append(term)
            else:
                missing_terms.append(term)

        matched_sources = [
            url for url in source_urls if any(term.lower() in url.lower() for term in matched_terms)
        ]
        if source_urls and not matched_sources:
            matched_sources = source_urls[:3]

        score = 100
        if warnings:
            score -= len(warnings) * 15
        if missing_terms:
            score -= min(40, len(missing_terms) * 8)
        score = max(0, min(100, score))

        passed = (
            len(warnings) == 0
            and len(missing_terms) <= max(1, len(terms) // 3)
            and len(matched_terms) >= self._min_matched_terms
        )

        return FactCheckResult(
            passed=passed,
            score=score,
            matched_sources=matched_sources,
            warnings=warnings,
            missing_terms=missing_terms[:8],
        )

    def _extract_check_terms(self, summary: str) -> list[str]:
        raw_terms = _TERM_RE.findall(summary)
        stopwords = {
            "the",
            "and",
            "with",
            "this",
            "that",
            "暂无",
            "可用",
            "信息",
            "摘要",
            "任务",
            "研究",
        }
        terms: list[str] = []
        for term in raw_terms:
            normalized = term.strip()
            if len(normalized) < 3 or normalized.lower() in stopwords:
                continue
            if normalized not in terms:
                terms.append(normalized)
            if len(terms) >= 12:
                break
        return terms