"""配置管理：从环境变量加载深度研究助手的运行参数。"""
import os
from enum import Enum
from typing import Any, Literal, Optional

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
        default=SearchAPI.TAVILY,
        title="搜索API",
        description="使用的网络搜索后端",
    )

    enable_notes: bool = Field(
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
    enable_browser_fetch: bool = Field(
        default=False,
        title="启用浏览器抓取",
        description="当 HTTP 无法补全页面正文时，尝试使用 Playwright 渲染页面",
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
    report_model_id: Optional[str] = Field(
        default=None,
        title="报告模型 ID",
        description="专用于最终报告生成的模型（不填则与 llm_model_id 一致）",
    )
    run_store_backend: str = Field(
        default="memory",
        title="研究运行存储后端",
        description="研究运行时间线存储后端：memory / sqlite",
    )
    run_store_db_path: str = Field(
        default="./data/research_runs.sqlite3",
        title="研究运行 SQLite 数据库路径",
        description="run_store_backend=sqlite 时使用的 SQLite 数据库路径",
    )
    max_concurrent_tasks: int = Field(
        default=4,
        ge=1,
        title="最大并发任务数",
        description="流式研究时同时执行搜索与总结的任务上限",
    )
    search_timeout_seconds: int = Field(
        default=60,
        ge=1,
        title="搜索超时秒数",
        description="单个任务搜索阶段的最大等待时间",
    )
    summary_timeout_seconds: int = Field(
        default=120,
        ge=1,
        title="总结超时秒数",
        description="单个任务总结阶段的最大等待时间",
    )
    search_fallback_chain: list[SearchAPI] = Field(
        default_factory=lambda: [SearchAPI.DUCKDUCKGO, SearchAPI.TAVILY],
        title="搜索后端降级链",
        description="主搜索后端失败时依次尝试的后端列表（不含主后端）",
    )
    research_mode: Literal["deep", "quick"] = Field(
        default="deep",
        title="研究模式",
        description="deep=完整规划与报告；quick=跳过规划，单次搜索总结即出结果",
    )
    enable_report_review: bool = Field(
        default=True,
        title="启用报告评审",
        description="报告生成后执行规则评审并推送 review_result 事件",
    )
    enable_fact_check: bool = Field(
        default=True,
        title="启用事实核对",
        description="任务总结完成后执行轻量 fact-check 并推送 fact_check_result 事件",
    )
    skills_workspace: str = Field(
        default="./skills",
        title="Skill 工作区",
        description="按需加载 SKILL.md 指引的目录",
    )
    research_pipeline: str = Field(
        default="plan,search,summarize,fact_check,report,review",
        title="研究流水线阶段",
        description="逗号分隔阶段列表，用于开关 fact_check / review 等步骤",
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
            "report_model_id": os.getenv("REPORT_MODEL_ID"),
            "llm_base_url": os.getenv("LLM_BASE_URL"),
            "lmstudio_base_url": os.getenv("LMSTUDIO_BASE_URL"),
            "ollama_base_url": os.getenv("OLLAMA_BASE_URL"),
            "max_web_research_loops": os.getenv("MAX_WEB_RESEARCH_LOOPS"),
            "fetch_full_page": os.getenv("FETCH_FULL_PAGE"),
            "enable_browser_fetch": os.getenv("ENABLE_BROWSER_FETCH"),
            "strip_thinking_tokens": os.getenv("STRIP_THINKING_TOKENS"),
            "use_tool_calling": os.getenv("USE_TOOL_CALLING"),
            "search_api": os.getenv("SEARCH_API"),
            "enable_notes": os.getenv("ENABLE_NOTES"),
            "notes_workspace": os.getenv("NOTES_WORKSPACE"),
            "run_store_backend": os.getenv("RUN_STORE_BACKEND"),
            "run_store_db_path": os.getenv("RUN_STORE_DB_PATH"),
            "max_concurrent_tasks": os.getenv("MAX_CONCURRENT_TASKS"),
            "search_timeout_seconds": os.getenv("SEARCH_TIMEOUT_SECONDS"),
            "summary_timeout_seconds": os.getenv("SUMMARY_TIMEOUT_SECONDS"),
            "research_mode": os.getenv("RESEARCH_MODE"),
            "enable_report_review": os.getenv("ENABLE_REPORT_REVIEW"),
            "enable_fact_check": os.getenv("ENABLE_FACT_CHECK"),
            "skills_workspace": os.getenv("SKILLS_WORKSPACE"),
            "research_pipeline": os.getenv("RESEARCH_PIPELINE"),
        }

        # setdefault：别名不覆盖第一步已读取的值
        for key, value in env_aliases.items():
            if value is not None:
                raw_values.setdefault(key, value)

        fallback_raw = os.getenv("SEARCH_FALLBACK_CHAIN")
        if fallback_raw is not None and "search_fallback_chain" not in raw_values:
            raw_values["search_fallback_chain"] = [
                item.strip() for item in fallback_raw.split(",") if item.strip()
            ]

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

    def resolved_report_model(self) -> Optional[str]:
        """返回报告专用模型名称：优先取 report_model_id，回退到主模型。"""
        return self.report_model_id or self.resolved_model()

