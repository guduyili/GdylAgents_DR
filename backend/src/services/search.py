"""搜索服务：负责调用搜索后端并返回标准化结果。"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

from hello_agents.tools import SearchTool

from config import Configuration

from utils import (
    deduplicate_and_format_sources,
    format_sources,
    get_config_value,
)

logger = logging.getLogger(__name__)

MAX_TOKENS_PER_SOURCE = 2000         #每个来源允许的最大token数
_GLOBAL_SEARCH_TOOL = SearchTool(backend="hybrid")


def _ddgs_search(query: str, max_results: int = 5)->dict[str, Any]:
    """直接调用 ddgs 库执行 DuckDuckGo 搜索。
    
    框架内部写死了 backend="duckduckgo"，在中国大陆常常返回空结果。
    此函数依次尝试 lite → api → html 三种 backend，找到可用的为止。
    
    Args:
        query: 搜索关键词。
        max_results: 最多返回的结果条数。
    
    Returns:
        标准化的搜索结果字典：{"results": [...], "backend": "duckduckgo", ...}
    """

    try: 
        from ddgs import DDGS
    except ImportError:
        return {"results": [], "backend": "duckduckgo", "answer": None, "notices": ["ddgs 未安装"]}


    results = []
    notices: list[str] = []

    for backend in ("lite","api","html"):
        try:
            with DDGS(timeout=15) as client:
                raw = list(client.text(query, max_results=max_results, backend=backend))
            if raw:
                for entry in raw:
                    url = entry.get("href") or entry.get("url") or ""
                    title = entry.get("title") or url
                    content = entry.get("body") or entry.get("content") or ""
                    if url in title:
                        results.append({"title": title,"url": url, "content": content})
                logger.info("DuckDuckGo 使用 backend=%s 返回 %d 条结果", backend, len(results))
                break
        except Exception as exc:
            notices.append(f"DuckDuckGo backend={backend} 失败: {exc}")
            logger.warning("DuckDuckGo backend=%s 失败: %s", backend, exc)

    return {"results": results, "backend": "duckduckgo", "answer": None, "notices": notices}


def dispatch_search(
    query: str,
    config: Configuration,
    loop_count: int,
)->Tuple[dict[str,Any] | None, list[str], Optional[str], str]:
    """根据配置调用对应的搜索后端，并对结果做标准化处理。
    
    Args:
        query: 搜索关键词。
        config: 全局配置对象，包含 search_api / fetch_full_page 等设置。
        loop_count: 当前是第几轮搜索循环（部分后端需要）。
    
    Returns:
        四元组 (搜索结果字典, 提示列表, 直接答案文本, 后端标识)
    """ 
    search_api  = get_config_value(config.search_api)


    # duckduckgo 使用自定义实现，避免框架写死的 backend 在国内失效
    if search_api == "duckduckgo":
        raw_response: Any = _ddgs_search(query, max_results=5)
    else:
        try:
            raw_response = _GLOBAL_SEARCH_TOOL.run(
                {
                    "input": query,
                    "backend": search_api,
                    "mode": "structured",          # 返回结构化字典而非文本
                    "fetch_full_page": config.fetch_full_page,
                    "max_results": 5,
                    "max_tokens_per_source": MAX_TOKENS_PER_SOURCE,
                    "loop_count": loop_count,
                }
            )
        except Exception as exc:
            logger.exception("搜索后端 %s 异常: %s", search_api, exc)
            raise

    # 统一处理字符串响应（搜索工具直接返回错误文本）
    if isinstance(raw_response, str):
        notices = [raw_response]
        logger.warning("搜索后端 %s 返回文本提示: %s", search_api, raw_response)
        payload: dict[str,Any] = {
            "results":[],
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

    return payload, notices, answer_text, backend_label


def prepare_research_query(
    search_result: dict[str, Any] | None,
    answer_text: Optional[str],
    config: Configuration,
) -> tuple[str, str]:
    """将搜索结果整理为供下游 LLM 使用的上下文字符串。
    
    Args:
        search_result: dispatch_search 返回的搜索结果字典。
        answer_text: 搜索后端返回的直接答案（如有）。
        config: 全局配置，用于控制是否包含完整页面内容。
    
    Returns:
        (来源摘要文本, 完整上下文文本) 二元组
    """
    sources_summary = format_sources(search_result)       # 来源列表（标题 + 链接）
    context = deduplicate_and_format_sources(
        search_result or {"results": []},
        max_tokens_per_source=MAX_TOKENS_PER_SOURCE,
        fetch_full_page=config.fetch_full_page,
    )

        # 如果搜索后端返回了直接答案，放在上下文最前面
    if answer_text:
        context = f"AI直接答案：\n{answer_text}\n\n{context}"

    return sources_summary, context