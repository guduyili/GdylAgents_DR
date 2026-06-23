"""搜索服务：负责调用搜索后端并返回标准化结果。"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from config import Configuration
from services.search_backends import (
    FallbackSearchBackend,
    SearchBackend,
    SearchOutcome,
    create_configured_search_backend,
    prepare_research_context as _prepare_research_context_impl,
)

__all__ = [
    "dispatch_search",
    "prepare_research_context",
    "SearchBackend",
    "SearchOutcome",
    "create_configured_search_backend",
]


def dispatch_search(
    query: str,
    config: Configuration,
    loop_count: int,
) -> Tuple[dict[str, Any] | None, list[str], Optional[str], str]:
    """根据配置调用搜索后端（含降级链），并对结果做标准化处理。"""
    outcome = create_configured_search_backend(config).search(
        query,
        config=config,
        loop_count=loop_count,
    )
    return outcome.payload, outcome.notices, outcome.answer_text, outcome.backend_label


def prepare_research_context(
    search_result: dict[str, Any] | None,
    answer_text: Optional[str],
    config: Configuration,
) -> tuple[str, str]:
    """将搜索结果整理为供下游 LLM 使用的上下文字符串。"""
    return _prepare_research_context_impl(search_result, answer_text, config)