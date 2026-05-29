"""DeepResearchAgent 使用的 LLM 构造辅助函数。"""

from __future__ import annotations

from typing import Any, TypeVar

from hello_agents import HelloAgentsLLM

from config import Configuration

LLM = TypeVar("LLM")


def build_llm_kwargs(
    config: Configuration,
    *,
    model_override: str | None = None,
) -> dict[str, Any]:
    """根据运行配置构造 HelloAgentsLLM 所需的关键字参数。"""
    llm_kwargs: dict[str, Any] = {"temperature": 0.0}

    model_id = model_override or config.resolved_model()
    if model_id:
        llm_kwargs["model"] = model_id

    provider = (config.llm_provider or "").strip()
    if provider:
        llm_kwargs["provider"] = provider

    if provider == "ollama":
        llm_kwargs["base_url"] = config.sanitized_ollama_url()
        llm_kwargs["api_key"] = config.llm_api_key or "ollama"
    elif provider == "lmstudio":
        llm_kwargs["base_url"] = config.lmstudio_base_url
        if config.llm_api_key:
            llm_kwargs["api_key"] = config.llm_api_key
    else:
        if config.llm_base_url:
            llm_kwargs["base_url"] = config.llm_base_url
        if config.llm_api_key:
            llm_kwargs["api_key"] = config.llm_api_key

    return llm_kwargs


def create_llm(
    config: Configuration,
    *,
    model_override: str | None = None,
    llm_class: type[LLM] = HelloAgentsLLM,
) -> LLM:
    """使用统一的配置规则创建 LLM 实例。"""
    return llm_class(**build_llm_kwargs(config, model_override=model_override))
