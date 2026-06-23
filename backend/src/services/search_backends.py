"""Search backend adapters: Protocol-based search with optional fallback chain."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from hello_agents.tools import SearchTool

from config import Configuration
from utils import (
    deduplicate_and_format_sources,
    format_sources,
    get_config_value,
)

logger = logging.getLogger(__name__)

MAX_TOKENS_PER_SOURCE = 2000
_GLOBAL_SEARCH_TOOL = SearchTool(backend="hybrid")


@dataclass(frozen=True)
class SearchOutcome:
    """Normalized result from a single search backend invocation."""

    payload: dict[str, Any]
    notices: list[str]
    answer_text: str | None
    backend_label: str


class SearchBackend(Protocol):
    """Contract for pluggable search backends."""

    name: str

    def search(
        self,
        query: str,
        *,
        config: Configuration,
        loop_count: int,
    ) -> SearchOutcome: ...


def _normalize_search_response(
    raw_response: Any,
    *,
    search_api: str,
) -> SearchOutcome:
    """Convert a raw backend response into a SearchOutcome."""
    if isinstance(raw_response, str):
        notices = [raw_response]
        logger.warning("搜索后端 %s 返回文本提示: %s", search_api, raw_response)
        payload: dict[str, Any] = {
            "results": [],
            "backend": search_api,
            "answer": None,
            "notices": notices,
        }
    else:
        payload = raw_response
        notices = list(payload.get("notices") or [])

    backend_label = str(payload.get("backend") or search_api)
    answer_text = payload.get("answer")
    results = payload.get("results", [])

    if notices:
        for notice in notices:
            logger.info("搜索提示 (%s): %s", backend_label, notice)

    logger.info(
        "搜索完成 backend=%s resolved_backend=%s 有直接答案=%s 结果数=%s",
        search_api,
        backend_label,
        bool(answer_text),
        len(results),
    )

    return SearchOutcome(
        payload=payload,
        notices=notices,
        answer_text=answer_text,
        backend_label=backend_label,
    )


def _ddgs_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Direct DuckDuckGo search via ddgs with lite/api/html fallback."""
    try:
        from ddgs import DDGS
    except ImportError:
        return {"results": [], "backend": "duckduckgo", "answer": None, "notices": ["ddgs 未安装"]}

    results: list[dict[str, str]] = []
    notices: list[str] = []

    for backend in ("lite", "api", "html"):
        try:
            with DDGS(timeout=15) as client:
                raw = list(client.text(query, max_results=max_results, backend=backend))
            if raw:
                for entry in raw:
                    url = entry.get("href") or entry.get("url") or ""
                    title = entry.get("title") or url
                    content = entry.get("body") or entry.get("content") or ""
                    if url or title:
                        results.append({"title": title, "url": url, "content": content})
                logger.info("DuckDuckGo 使用 backend=%s 返回 %d 条结果", backend, len(results))
                break
        except Exception as exc:
            notices.append(f"DuckDuckGo backend={backend} 失败: {exc}")
            logger.warning("DuckDuckGo backend=%s 失败: %s", backend, exc)

    return {"results": results, "backend": "duckduckgo", "answer": None, "notices": notices}


class DuckDuckGoBackend:
    """DuckDuckGo search adapter."""

    name = "duckduckgo"

    def search(
        self,
        query: str,
        *,
        config: Configuration,
        loop_count: int,
    ) -> SearchOutcome:
        del config, loop_count
        return _normalize_search_response(_ddgs_search(query, max_results=5), search_api=self.name)


class TavilyBackend:
    """Tavily search adapter via hello_agents SearchTool."""

    name = "tavily"

    def search(
        self,
        query: str,
        *,
        config: Configuration,
        loop_count: int,
    ) -> SearchOutcome:
        raw_response = _GLOBAL_SEARCH_TOOL.run(
            {
                "input": query,
                "backend": self.name,
                "mode": "structured",
                "fetch_full_page": config.fetch_full_page,
                "max_results": 5,
                "max_tokens_per_source": MAX_TOKENS_PER_SOURCE,
                "loop_count": loop_count,
            }
        )
        return _normalize_search_response(raw_response, search_api=self.name)


class SearXNGBackend:
    """SearXNG search adapter via hello_agents SearchTool."""

    name = "searxng"

    def search(
        self,
        query: str,
        *,
        config: Configuration,
        loop_count: int,
    ) -> SearchOutcome:
        raw_response = _GLOBAL_SEARCH_TOOL.run(
            {
                "input": query,
                "backend": self.name,
                "mode": "structured",
                "fetch_full_page": config.fetch_full_page,
                "max_results": 5,
                "max_tokens_per_source": MAX_TOKENS_PER_SOURCE,
                "loop_count": loop_count,
            }
        )
        return _normalize_search_response(raw_response, search_api=self.name)


class GenericSearchToolBackend:
    """Adapter for backends routed through hello_agents SearchTool."""

    def __init__(self, name: str) -> None:
        self.name = name

    def search(
        self,
        query: str,
        *,
        config: Configuration,
        loop_count: int,
    ) -> SearchOutcome:
        raw_response = _GLOBAL_SEARCH_TOOL.run(
            {
                "input": query,
                "backend": self.name,
                "mode": "structured",
                "fetch_full_page": config.fetch_full_page,
                "max_results": 5,
                "max_tokens_per_source": MAX_TOKENS_PER_SOURCE,
                "loop_count": loop_count,
            }
        )
        return _normalize_search_response(raw_response, search_api=self.name)


def create_search_backend(backend_name: str) -> SearchBackend:
    """Instantiate a concrete search backend by name."""
    if backend_name == "duckduckgo":
        return DuckDuckGoBackend()
    if backend_name == "tavily":
        return TavilyBackend()
    if backend_name == "searxng":
        return SearXNGBackend()
    return GenericSearchToolBackend(backend_name)


class FallbackSearchBackend:
    """Primary backend with configured fallback chain."""

    def __init__(self, config: Configuration) -> None:
        self._config = config
        self._backends = self._resolve_backend_names(config)

    @property
    def name(self) -> str:
        return self._backends[0] if self._backends else "unknown"

    def _resolve_backend_names(self, config: Configuration) -> list[str]:
        primary = get_config_value(config.search_api)
        backends = [primary]
        for fallback in config.search_fallback_chain:
            fallback_value = get_config_value(fallback)
            if fallback_value not in backends:
                backends.append(fallback_value)
        return backends

    def search(
        self,
        query: str,
        *,
        config: Configuration,
        loop_count: int,
    ) -> SearchOutcome:
        primary_backend = self._backends[0]
        notices: list[str] = []
        last_error: Exception | None = None

        for index, backend_name in enumerate(self._backends):
            backend = create_search_backend(backend_name)
            try:
                outcome = backend.search(query, config=config, loop_count=loop_count)
            except Exception as exc:
                last_error = exc
                notice = f"搜索后端 {backend_name} 失败: {exc}"
                notices.append(notice)
                logger.warning("搜索后端 %s 异常，准备尝试降级: %s", backend_name, exc)
                continue

            merged_notices = list(outcome.notices)
            if index > 0:
                merged_notices.insert(
                    0,
                    f"主搜索后端 {primary_backend} 失败，已切换到 {outcome.backend_label}",
                )
            if notices:
                merged_notices = notices + merged_notices

            return SearchOutcome(
                payload=outcome.payload,
                notices=merged_notices,
                answer_text=outcome.answer_text,
                backend_label=outcome.backend_label,
            )

        if last_error is not None:
            logger.error(
                "所有搜索后端均失败 primary=%s fallbacks=%s error=%s",
                primary_backend,
                self._backends[1:],
                last_error,
            )

        empty_payload: dict[str, Any] = {
            "results": [],
            "backend": primary_backend,
            "answer": None,
            "notices": notices,
        }
        if last_error is not None:
            empty_payload["notices"].append(f"搜索失败: {last_error}")

        return SearchOutcome(
            payload=empty_payload,
            notices=notices,
            answer_text=None,
            backend_label=primary_backend,
        )


def create_configured_search_backend(config: Configuration) -> SearchBackend:
    """Build the search backend used by TaskExecutor for the current configuration."""
    return FallbackSearchBackend(config)


def prepare_research_context(
    search_result: dict[str, Any] | None,
    answer_text: Optional[str],
    config: Configuration,
) -> tuple[str, str]:
    """将搜索结果整理为供下游 LLM 使用的上下文字符串。"""
    sources_summary = format_sources(search_result)
    context = deduplicate_and_format_sources(
        search_result or {"results": []},
        max_tokens_per_source=MAX_TOKENS_PER_SOURCE,
        fetch_full_page=config.fetch_full_page,
    )

    if answer_text:
        context = f"AI直接答案：\n{answer_text}\n\n{context}"

    return sources_summary, context