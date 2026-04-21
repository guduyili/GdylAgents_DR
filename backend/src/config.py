"""配置管理：从环境变量加载深度研究助手的运行参数。"""
import os
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

class SearchAPI(Enum):
    """ 支持的搜索后端枚举"""
    PERPLEXITY = "perplexity" 
    TAVILY ="tavily"
    DUCKDUCKGO = "duckduckgo"
    SEAGXNG = "searxng"
    ADVANCED = "advanced"


class Configuration(BaseModel):
    """
    深度研究助手的全局配置项。
    """
    max_web_research_loops: int = Field(
        default=3,
        title="研究深度",
        description= "执行网络搜索的最大轮次",
    )

    local_llm: str = Field(
        default="llama3.2",
        title="本地模型名称",
        description="Ollama / LMStudio 中部署的模型名称",
    )
    llm_provider: str = Field(
        default="ollama",
        title="LLM 提供商",
        description="模型服务商标识：ollama / lmstudio / custom",
    )

    search_api: SearchAPI = Field(
        default=SearchAPI.DUCKDUCKGO,
        title="搜索API",
        description="使用的网络搜索后端",
    )

    enable_noted: bool = Field(
        default=True,
        title="启用笔记",
        description="是否将任务进展持久化到NoteTool",
    )

    notes_workspace: str = Field(
        default="./note",
        title="笔记目录",
        description="NoteTool 存储笔记文件的本地目录",
    )

    fetch_full_page: bool = Field(
        default=True,
        title="获取完整页面",
        description="搜索时是否抓取完整页面内容",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        title="Ollama 地址",
        description="Ollama 服务的 base URL（不含 /v1）",
    )
    lmstudio_base_url: str = Field(
        default="http://localhost:1234/v1",
        title="LMStudio 地址",
        description="LMStudio OpenAI 兼容接口的 base URL",
    )
    strip_thinking_tokens: bool = Field(
        default=True,
        title="剥除思考标签",
        description="是否从模型响应中移除 <think> 推理片段",
    )
    use_tool_calling: bool = Field(
        default=False,
        title="使用工具调用",
        description="使用原生 function call 替代 JSON 模式输出结构化内容",
    )
    llm_api_key: Optional[str] = Field(
        default=None,
        title="LLM API Key",
        description="使用自定义 OpenAI 兼容服务时的 API 密钥",
    )
    llm_base_url: Optional[str] = Field(
        default=None,
        title="LLM Base URL",
        description="使用自定义 OpenAI 兼容服务时的接口地址",
    )
    llm_model_id: Optional[str] = Field(
        default=None,
        title="LLM 模型 ID",
        description="使用自定义 OpenAI 兼容服务时的模型名称",
    )


    @classmethod
    def from_env(cls, overrides: Optional[dict[str, Any]] = None) -> "Configuration":
        """从环境变量读取配置，支持外部传入的覆盖参数。
        
        优先级：overrides 参数 > 环境变量别名 > 字段名对应的环境变量 > 字段默认值
        """
        raw_values: dict[str, Any] = {}

        # 第一步：按字段名大写映射读取同名环境变量
        for field_name in cls.model_fields.keys():
            env_key = field_name.upper()
            if env_key in os.environ:
                raw_values[field_name] = os.environ[env_key]

        # 第二步：读取显式定义的环境变量别名（支持旧版命名）
        env_aliases = {
            "local_llm": os.getenv("LOCAL_LLM"),
            "llm_provider": os.getenv("LLM_PROVIDER"),
            "llm_api_key": os.getenv("LLM_API_KEY"),
            "llm_model_id": os.getenv("LLM_MODEL_ID"),
            "llm_base_url": os.getenv("LLM_BASE_URL"),
            "lmstudio_base_url": os.getenv("LMSTUDIO_BASE_URL"),
            "ollama_base_url": os.getenv("OLLAMA_BASE_URL"),
            "max_web_research_loops": os.getenv("MAX_WEB_RESEARCH_LOOPS"),
            "fetch_full_page": os.getenv("FETCH_FULL_PAGE"),
            "strip_thinking_tokens": os.getenv("STRIP_THINKING_TOKENS"),
            "use_tool_calling": os.getenv("USE_TOOL_CALLING"),
            "search_api": os.getenv("SEARCH_API"),
            "enable_notes": os.getenv("ENABLE_NOTES"),
            "notes_workspace": os.getenv("NOTES_WORKSPACE"),
        }

        # setdefault：别名不覆盖第一步已读取的值
        for key, value in env_aliases.items():
            if value is not None:
                raw_values.setdefault(key, value)

        # 第三步：外部 overrides 优先级最高
        if overrides:
            for key, value in overrides.items():
                if value is not None:
                    raw_values[key] = value

        return cls(**raw_values)

    def sanitized_ollama_url(self) -> str:
        """返回确保以 /v1 结尾的 Ollama 接口地址。
        
        OpenAI 客户端要求 base_url 以 /v1 结尾，此方法自动补全。
        """
        base = self.ollama_base_url.rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        return base

    def resolved_model(self) -> Optional[str]:
        """返回最终使用的模型名称：优先取 llm_model_id，回退到 local_llm。"""
        return self.llm_model_id or self.local_llm

