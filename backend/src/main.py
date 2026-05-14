"""FastAPI HTTP 入口：将 DeepResearchAgent 封装为 REST 接口。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from dotenv import load_dotenv

# 优先加载 src/.env，其次加载上级目录的 .env
_here = Path(__file__).parent
load_dotenv(_here / ".env")
load_dotenv(_here.parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from config import Configuration, SearchAPI
from agent import DeepResearchAgent
from models import TodoItem


# ────────────────────────────────────────────────────
# 日志配置
# ────────────────────────────────────────────────────
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>{function}</cyan> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)


# ────────────────────────────────────────────────────
# 请求/响应数据模型
# ────────────────────────────────────────────────────
class ResearchRequest(BaseModel):
    """发起研究请求的请求体。"""

    topic: str = Field(..., description="用户提交的研究主题")
    search_api: SearchAPI | None = Field(
        default=None,
        description="覆盖环境变量中配置的搜索后端（可选）",
    )
    todo_items: list["TodoItemRequest"] | None = Field(
        default=None,
        description="用户确认或编辑后的任务清单；为空时后端自动规划",
    )


class TodoItemRequest(BaseModel):
    """前端提交的可编辑研究任务。"""

    id: int | None = Field(default=None, description="任务编号，可由后端重新规范化")
    title: str = Field(..., description="任务标题")
    intent: str = Field(..., description="任务目标")
    query: str = Field(..., description="检索查询")


class ResearchPlanResponse(BaseModel):
    """研究规划接口的响应体。"""

    topic: str = Field(..., description="研究主题")
    todo_items: list[dict[str, Any]] = Field(default_factory=list, description="规划任务列表")


class ResearchResponse(BaseModel):
    """同步研究接口的响应体。"""

    report_markdown: str = Field(
        ..., description="Markdown 格式的完整研究报告"
    )
    todo_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="所有子任务及其摘要和来源",
    )


# ────────────────────────────────────────────────────
# 工具函数
# ────────────────────────────────────────────────────
def _mask_secret(value: Optional[str], visible: int = 4) -> str:
    """对敏感字符串（如 API Key）做掩码处理，仅显示首尾几位。"""
    if not value:
        return "unset"
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}...{value[-visible:]}"


def _build_config(payload: ResearchRequest) -> Configuration:
    """根据请求参数构建配置对象（允许请求级别覆盖环境变量中的搜索后端）。"""
    overrides: Dict[str, Any] = {}
    if payload.search_api is not None:
        overrides["search_api"] = payload.search_api
    return Configuration.from_env(overrides=overrides)


def _normalize_todo_items(items: list[TodoItemRequest] | None, topic: str) -> list[TodoItem] | None:
    """将前端提交的任务清单转换为内部 TodoItem，并重新分配连续 ID。"""
    if items is None:
        return None

    normalized: list[TodoItem] = []
    for index, item in enumerate(items, start=1):
        title = item.title.strip()
        intent = item.intent.strip()
        query = item.query.strip() or topic.strip()
        if not title or not intent or not query:
            continue
        normalized.append(
            TodoItem(
                id=index,
                title=title,
                intent=intent,
                query=query,
            )
        )

    if not normalized:
        raise ValueError("任务清单不能为空")
    return normalized


def _serialize_todo_item(item: TodoItem) -> dict[str, Any]:
    """将内部 TodoItem 转为 API 响应字典。"""
    return {
        "id": item.id,
        "title": item.title,
        "intent": item.intent,
        "query": item.query,
        "status": item.status,
        "summary": item.summary,
        "sources_summary": item.sources_summary,
        "note_id": item.note_id,
        "note_path": item.note_path,
    }


# ────────────────────────────────────────────────────
# FastAPI 应用工厂
# ────────────────────────────────────────────────────
def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app = FastAPI(title="HelloAgents Deep Researcher")

    # 允许前端跨域访问（开发环境使用 *，生产环境应收紧 origins）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def log_startup_configuration() -> None:
        """服务启动时打印当前配置，方便排查环境问题。"""
        config = Configuration.from_env()

        if config.llm_provider == "ollama":
            base_url = config.sanitized_ollama_url()
        elif config.llm_provider == "lmstudio":
            base_url = config.lmstudio_base_url
        else:
            base_url = config.llm_base_url or "unset"

        logger.info(
            "配置加载完成: provider=%s model=%s base_url=%s search_api=%s "
            "max_loops=%s fetch_full_page=%s tool_calling=%s strip_thinking=%s api_key=%s",
            config.llm_provider,
            config.resolved_model() or "unset",
            base_url,
            (config.search_api.value if isinstance(config.search_api, SearchAPI) else config.search_api),
            config.max_web_research_loops,
            config.fetch_full_page,
            config.use_tool_calling,
            config.strip_thinking_tokens,
            _mask_secret(config.llm_api_key),
        )

    @app.get("/healthz")
    def health_check() -> Dict[str, str]:
        """健康检查接口，供 k8s/负载均衡器探活使用。"""
        return {"status": "ok"}

    @app.post("/research/plan", response_model=ResearchPlanResponse)
    def plan_research(payload: ResearchRequest) -> ResearchPlanResponse:
        """仅生成研究任务清单，供前端展示和编辑。"""
        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config)
            todo_items = agent.plan(payload.topic)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("研究规划生成失败")
            raise HTTPException(status_code=500, detail="研究规划生成失败") from exc

        return ResearchPlanResponse(
            topic=payload.topic,
            todo_items=[_serialize_todo_item(item) for item in todo_items],
        )

    @app.post("/research", response_model=ResearchResponse)
    def run_research(payload: ResearchRequest) -> ResearchResponse:
        """同步研究接口：等待全部任务完成后返回完整报告。
        
        适合调试或对延迟不敏感的场景。
        """
        try:
            config = _build_config(payload)
            todo_items = _normalize_todo_items(payload.todo_items, payload.topic)
            agent = DeepResearchAgent(config=config) 
            result = agent.run(payload.topic, todo_items=todo_items)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="研究流程执行失败") from exc

        todo_payload = [
            {
                "id": item.id,
                "title": item.title,
                "intent": item.intent,
                "query": item.query,
                "status": item.status,
                "summary": item.summary,
                "sources_summary": item.sources_summary,
                "note_id": item.note_id,
                "note_path": item.note_path,
            }
            for item in result.todo_items
        ]

        return ResearchResponse(
            report_markdown=(result.report_markdown or result.running_summary or ""),
            todo_items=todo_payload,
        )

    @app.post("/research/stream")
    def stream_research(payload: ResearchRequest) -> StreamingResponse:
        """流式研究接口（SSE）：边研究边推送进度事件，前端可实时展示。
        
        每条事件格式：data: {JSON}\n\n
        事件 type 字段包括：status / todo_list / task_status / sources /
                           task_summary_chunk / final_report / done / error
        """
        try:
            config = _build_config(payload)
            todo_items = _normalize_todo_items(payload.todo_items, payload.topic)
            agent = DeepResearchAgent(config=config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        def event_iterator() -> Iterator[str]:
            """将 Agent 的事件字典序列化为 SSE 格式字符串逐条推送。"""
            try:
                for event in agent.run_stream(payload.topic, todo_items=todo_items):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:
                logger.exception("流式研究执行失败")
                error_payload = {"type": "error", "detail": str(exc)}
                yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_iterator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )






    @app.get("/notes/reports")
    def list_reports() -> list[dict]:
        """返回所有 conclusion 类型的笔记（即最终研究报告）列表，按时间倒序。"""
        index_path = Path(__file__).parent / "note" / "notes_index.json"
        if not index_path.exists():
            return []
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        notes = data.get("notes", [])
        reports = [
            {
                "id": n["id"],
                "title": n.get("title", ""),
                "created_at": n.get("created_at", ""),
                "tags": n.get("tags", []),
            }
            for n in notes
            if n.get("type") == "conclusion"
        ]
        return sorted(reports, key=lambda x: x["created_at"], reverse=True)

    @app.get("/notes/reports/{note_id}")
    def get_report(note_id: str) -> dict:
        """获取单条 conclusion 报告的完整 Markdown 内容。"""
        import re
        # 安全校验：note_id 只允许字母、数字、下划线、连字符
        if not re.match(r'^[a-zA-Z0-9_\-]+$', note_id):
            raise HTTPException(status_code=400, detail="非法的报告 ID")
        note_dir = (Path(__file__).parent / "note").resolve()
        note_path = (note_dir / f"{note_id}.md").resolve()
        # 确保解析后的路径仍在 note 目录内，防止路径穿越
        if not str(note_path).startswith(str(note_dir)):
            raise HTTPException(status_code=400, detail="非法的报告 ID")
        if not note_path.exists():
            raise HTTPException(status_code=404, detail="报告不存在")
        content = note_path.read_text(encoding="utf-8")
        # 解析 frontmatter（第一行可能是 YAML --- 块）
        title = note_id
        body = content
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                frontmatter = content[3:end].strip()
                body = content[end + 3:].strip()
                for line in frontmatter.splitlines():
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip().strip('"').strip("'")
        return {"id": note_id, "title": title, "content": body}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    # 开发模式：开启 reload，修改代码后自动重启
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
