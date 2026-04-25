"""各服务模块共用的工具函数。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Union


CHARS_PER_TOKEN = 4

logger = logging.getLogger(__name__)



def get_config_value(value: Any)->str:
    """将配置项值统一转为字符串。
    
    配置项可能是字符串或 Enum，此函数统一返回原始字符串值。
    """

    return value if isinstance(value,str) else value.value


def strip_thinking_tokens(text: str) -> str:
    """移除模型响应中的 <think>...</think> 推理过程片段。
    
    部分模型（如 DeepSeek-R1）会在响应中插入思考过程，
    最终呈现给用户时需要将其剥除。
    """
    while "<think>" in text and "</think>" in text:
        start = text.find("<think>")
        end = text.find("</think>") + len("</think>")
        text = text[:start] + text[end:]

    return text

def deduplicate_and_format_sources(
    search_response: Dict[str,Any] | List[Dict[str,Any]],
    max_tokens_per_source: int,
    *,
    fetch_full_page: bool = False,
) ->str:
    """对搜索结果去重并格式化为 LLM 可用的上下文字符串。
    
    Args:
        search_response: 搜索结果，可以是包含 results 键的字典，或直接的列表。
        max_tokens_per_source: 每个来源允许的最大 token 数（用于截断长文本）。
        fetch_full_page: 是否包含完整页面内容（raw_content）。
    
    Returns:
        格式化后的来源文本，供下游 prompt 使用。
    """
    # 统一转为列表格式
    if isinstance(search_response,dict):
        sources_list = search_response.get("results",[])
    else:
        sources_list = search_response
    
    # 按URL 去重 保留首次出现的条目
    unique_sources: dict[str,Dict[str,Any]] = {}
    for source in sources_list:
        url = source.get("url")
        if not url:
            continue
        if url not in unique_sources:
            unique_sources[url] = source
        
    # 逐条拼接格式化文本
    formatted_parts: List[str] = []
    for source in unique_sources.values():
        title = source.get("title") or source.get("url", "")
        content = source.get("content", "")
        formatted_parts.append(f"信息来源: {title}\n\n")
        formatted_parts.append(f"URL: {source.get('url', '')}\n\n")
        formatted_parts.append(f"信息内容: {content}\n\n")

        # 如果需要完整页面内容 附加 raw_content 并截断超长文本
        if fetch_full_page:
            raw_content = source.get("raw_content")
            if raw_content is None:
                logger.debug("来源 %s 缺少 raw_content 字段", source.get("url", ""))
                raw_content = ""
            char_limit = max_tokens_per_source * CHARS_PER_TOKEN
            if len(raw_content) > char_limit:
                raw_content = f"{raw_content[:char_limit]}... [truncated]"
            formatted_parts.append(
                f"详细信息内容限制为 {max_tokens_per_source} 个 token: {raw_content}\n\n"
            )

    return "".join(formatted_parts).strip()



def format_sources(search_results: Dict[str, Any] | None) -> str:
    """将搜索结果整理为简短的来源列表（标题 + 链接）。
    
    Returns:
        每行一条 "* 标题 : URL" 格式的字符串，供报告引用。
    """
    if not search_results:
        return ""

    results = search_results.get("results", [])
    return "\n".join(
        f"* {item.get('title', item.get('url', ''))} : {item.get('url', '')}"
        for item in results
        if item.get("url")
    )