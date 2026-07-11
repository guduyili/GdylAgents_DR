"""历史研究报告的 RAG 检索（Phase1：无向量依赖的词项检索）。

设计目标：
- 从 NOTES_WORKSPACE 加载 conclusion 类报告并分块
- 按 query 返回 top-k 相关片段，供规划 Prompt 注入
- 检索失败时返回空结果，不阻断主研究流程
- 后续可用实现同一接口的 Embedding 后端替换
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}|[\u4e00-\u9fff]+")
_NOTE_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


@dataclass(frozen=True)
class ReportChunk:
    """一条可检索的报告片段。"""

    chunk_id: str
    note_id: str
    title: str
    text: str
    score: float = 0.0


class ReportRetriever(Protocol):
    """报告检索器协议，便于 Phase2 替换为向量实现。"""

    def retrieve(self, query: str, *, top_k: int | None = None) -> list[ReportChunk]:
        """按 query 返回相关片段。"""

    def format_context(self, chunks: list[ReportChunk]) -> str:
        """将片段格式化为可注入 Prompt 的上下文。"""


def tokenize(text: str) -> list[str]:
    """简易分词：英文词 + 中文连续字串拆成 bigram。

    不依赖 jieba，适合 Phase1；中文靠字 bigram 近似匹配。
    """
    if not text:
        return []

    text = text.lower().strip()
    tokens: list[str] = []
    for match in _TOKEN_RE.findall(text):
        if re.fullmatch(r"[a-z0-9]{2,}", match):
            tokens.append(match)
            continue
        # 中文：单字过短，使用重叠 bigram
        if len(match) == 1:
            tokens.append(match)
        else:
            for i in range(len(match) - 1):
                tokens.append(match[i : i + 2])
            if len(match) >= 3:
                tokens.append(match)  # 整词加权机会
    return tokens


def chunk_text(
    text: str,
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
) -> list[str]:
    """按字符长度切块，保留重叠，尽量在段落边界断开。"""
    body = (text or "").strip()
    if not body:
        return []

    chunk_size = max(64, chunk_size)
    chunk_overlap = max(0, min(chunk_overlap, chunk_size // 2))

    chunks: list[str] = []
    start = 0
    n = len(body)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            # 优先在段落或换行处切开
            window = body[start:end]
            break_at = max(window.rfind("\n\n"), window.rfind("\n"))
            if break_at >= chunk_size // 3:
                end = start + break_at + 1
        piece = body[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - chunk_overlap, start + 1)
    return chunks


def _strip_frontmatter(content: str) -> tuple[str, str]:
    """剥离 YAML frontmatter，返回 (title_hint, body)。"""
    title = ""
    body = content
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            frontmatter = content[3:end].strip()
            body = content[end + 3 :].strip()
            for line in frontmatter.splitlines():
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip('"').strip("'")
    return title, body


def _safe_note_path(workspace: Path, note_id: str) -> Path | None:
    if not _NOTE_ID_RE.match(note_id):
        return None
    path = (workspace / f"{note_id}.md").resolve()
    try:
        path.relative_to(workspace.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def load_report_documents(notes_workspace: str | Path) -> list[tuple[str, str, str]]:
    """从笔记目录加载报告文档。

    Returns:
        list of (note_id, title, body)
    """
    workspace = Path(notes_workspace)
    if not workspace.is_dir():
        logger.debug("RAG notes workspace 不存在: %s", workspace)
        return []

    conclusion_ids: set[str] | None = None
    index_path = workspace / "notes_index.json"
    if index_path.is_file():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            notes = data.get("notes") or []
            conclusion_ids = {
                str(n["id"])
                for n in notes
                if isinstance(n, dict)
                and n.get("id")
                and n.get("type") in {"conclusion", "report"}
            }
            # 索引存在但还没有 conclusion 时，回退扫描全部 md，便于手工放文件调试
            if not conclusion_ids:
                conclusion_ids = None
        except Exception:
            logger.exception("读取 notes_index.json 失败，回退为扫描 md 文件")
            conclusion_ids = None

    documents: list[tuple[str, str, str]] = []
    if conclusion_ids is not None:
        for note_id in sorted(conclusion_ids):
            path = _safe_note_path(workspace, note_id)
            if path is None:
                continue
            raw = path.read_text(encoding="utf-8", errors="ignore")
            title_hint, body = _strip_frontmatter(raw)
            title = title_hint or note_id
            if body.strip():
                documents.append((note_id, title, body))
        return documents

    for path in sorted(workspace.glob("*.md")):
        note_id = path.stem
        if not _NOTE_ID_RE.match(note_id):
            continue
        safe = _safe_note_path(workspace, note_id)
        if safe is None:
            continue
        raw = safe.read_text(encoding="utf-8", errors="ignore")
        title_hint, body = _strip_frontmatter(raw)
        title = title_hint or note_id
        if body.strip():
            documents.append((note_id, title, body))
    return documents


def build_chunks_from_documents(
    documents: list[tuple[str, str, str]],
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
) -> list[ReportChunk]:
    """将文档列表切成 ReportChunk。"""
    chunks: list[ReportChunk] = []
    for note_id, title, body in documents:
        pieces = chunk_text(body, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        for idx, piece in enumerate(pieces):
            chunks.append(
                ReportChunk(
                    chunk_id=f"{note_id}#{idx}",
                    note_id=note_id,
                    title=title,
                    text=piece,
                )
            )
    return chunks


def score_chunk(query_tokens: list[str], chunk: ReportChunk) -> float:
    """基于词项重叠的简易相关分；标题命中额外加权。"""
    if not query_tokens:
        return 0.0

    q_set = set(query_tokens)
    body_tokens = set(tokenize(chunk.text))
    title_tokens = set(tokenize(chunk.title))

    body_hits = len(q_set & body_tokens)
    title_hits = len(q_set & title_tokens)
    if body_hits == 0 and title_hits == 0:
        return 0.0

    # 标题命中权重更高
    raw = body_hits + 2.0 * title_hits
    return raw / max(len(q_set), 1)


class LexicalReportRetriever:
    """Phase1：基于词项重叠的报告检索器。"""

    def __init__(
        self,
        notes_workspace: str | Path,
        *,
        top_k: int = 4,
        chunk_size: int = 500,
        chunk_overlap: int = 80,
        max_context_chars: int = 3000,
    ) -> None:
        self.notes_workspace = Path(notes_workspace)
        self.top_k = max(1, top_k)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_context_chars = max(64, max_context_chars)
        self._chunks: list[ReportChunk] | None = None

    def rebuild_index(self) -> int:
        """从磁盘重新加载并分块，返回 chunk 数量。"""
        documents = load_report_documents(self.notes_workspace)
        self._chunks = build_chunks_from_documents(
            documents,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        logger.info(
            "RAG 索引已重建: workspace=%s docs=%d chunks=%d",
            self.notes_workspace,
            len(documents),
            len(self._chunks),
        )
        return len(self._chunks)

    def _ensure_index(self) -> list[ReportChunk]:
        if self._chunks is None:
            self.rebuild_index()
        assert self._chunks is not None
        return self._chunks

    def retrieve(self, query: str, *, top_k: int | None = None) -> list[ReportChunk]:
        """检索与 query 最相关的报告片段。"""
        try:
            chunks = self._ensure_index()
        except Exception:
            logger.exception("RAG 索引加载失败")
            return []

        if not chunks or not (query or "").strip():
            return []

        limit = max(1, top_k or self.top_k)
        q_tokens = tokenize(query)
        if not q_tokens:
            return []

        scored: list[ReportChunk] = []
        for chunk in chunks:
            s = score_chunk(q_tokens, chunk)
            if s <= 0:
                continue
            scored.append(
                ReportChunk(
                    chunk_id=chunk.chunk_id,
                    note_id=chunk.note_id,
                    title=chunk.title,
                    text=chunk.text,
                    score=s,
                )
            )

        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:limit]

    def format_context(self, chunks: list[ReportChunk]) -> str:
        """格式化为规划 Prompt 可用的历史研究上下文。"""
        if not chunks:
            return ""

        parts: list[str] = []
        used = 0
        limit = self.max_context_chars
        for i, chunk in enumerate(chunks, start=1):
            header = f"[{i}] note_id={chunk.note_id} title={chunk.title} score={chunk.score:.2f}"
            body = chunk.text.strip()
            sep_len = 2 if parts else 0
            budget = limit - used - sep_len
            if budget <= 40:
                break

            block = f"{header}\n{body}"
            if len(block) > budget:
                # 至少保留 header；正文按剩余预算截断
                header_len = len(header) + 1
                body_budget = budget - header_len - 1  # 省略号
                if body_budget < 20:
                    break
                block = f"{header}\n{body[:body_budget]}…"

            parts.append(block)
            used += sep_len + len(block)
            if used >= limit:
                break

        return "\n\n".join(parts)

    def invalidate(self) -> None:
        """丢弃内存索引，下次 retrieve 时重建。"""
        self._chunks = None


def create_report_retriever_from_config(config: object) -> LexicalReportRetriever | None:
    """根据 Configuration 创建检索器；未启用时返回 None。"""
    enable = bool(getattr(config, "enable_report_rag", False))
    if not enable:
        return None

    workspace = getattr(config, "notes_workspace", None) or "./note"
    return LexicalReportRetriever(
        workspace,
        top_k=int(getattr(config, "rag_top_k", 4) or 4),
        chunk_size=int(getattr(config, "rag_chunk_size", 500) or 500),
        chunk_overlap=int(getattr(config, "rag_chunk_overlap", 80) or 80),
        max_context_chars=int(getattr(config, "rag_max_context_chars", 3000) or 3000),
    )
