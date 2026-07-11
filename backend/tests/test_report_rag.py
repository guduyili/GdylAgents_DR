"""Phase1 report RAG: chunking, lexical retrieve, format_context."""

from __future__ import annotations

import json
from pathlib import Path

from config import Configuration
from services.report_rag import (
    LexicalReportRetriever,
    ReportChunk,
    build_chunks_from_documents,
    chunk_text,
    create_report_retriever_from_config,
    load_report_documents,
    score_chunk,
    tokenize,
)


def test_tokenize_english_and_cjk_bigrams() -> None:
    tokens = tokenize("Agent 智能体系统")
    assert "agent" in tokens
    assert any(len(t) == 2 for t in tokens if not t.isascii())


def test_chunk_text_respects_size_and_overlap() -> None:
    text = "段落甲。\n\n" + ("内容" * 100) + "\n\n段落乙。"
    chunks = chunk_text(text, chunk_size=80, chunk_overlap=20)
    assert len(chunks) >= 2
    assert all(len(c) <= 120 for c in chunks)


def test_load_and_retrieve_prefers_matching_document(tmp_path: Path) -> None:
    workspace = tmp_path / "notes"
    workspace.mkdir()
    (workspace / "note_agent.md").write_text(
        "---\ntitle: Agent 工程实践\n---\n\n"
        "本文讨论 Agent 编排、工具调用与可观测性。SSE 与取消链路是关键。\n",
        encoding="utf-8",
    )
    (workspace / "note_cooking.md").write_text(
        "---\ntitle: 家常菜谱\n---\n\n红烧肉需要五花肉、冰糖和生抽。\n",
        encoding="utf-8",
    )
    index = {
        "notes": [
            {"id": "note_agent", "type": "conclusion", "title": "Agent 工程实践"},
            {"id": "note_cooking", "type": "conclusion", "title": "家常菜谱"},
        ]
    }
    (workspace / "notes_index.json").write_text(
        json.dumps(index, ensure_ascii=False),
        encoding="utf-8",
    )

    docs = load_report_documents(workspace)
    assert {d[0] for d in docs} == {"note_agent", "note_cooking"}

    retriever = LexicalReportRetriever(workspace, top_k=2, chunk_size=200)
    hits = retriever.retrieve("Agent 工具调用 可观测")
    assert hits
    assert hits[0].note_id == "note_agent"
    assert hits[0].score > 0

    cooking_hits = retriever.retrieve("红烧肉 五花肉 菜谱")
    assert cooking_hits
    assert cooking_hits[0].note_id == "note_cooking"

    ctx = retriever.format_context(hits)
    assert "note_agent" in ctx
    assert "Agent" in ctx or "agent" in ctx.lower()


def test_score_chunk_title_boost() -> None:
    chunk = ReportChunk(
        chunk_id="n#0",
        note_id="n",
        title="深度研究 Agent",
        text="无关正文内容填充。",
    )
    q = tokenize("Agent 研究")
    assert score_chunk(q, chunk) > 0


def test_format_context_respects_max_chars() -> None:
    retriever = LexicalReportRetriever(".", max_context_chars=120)
    chunks = [
        ReportChunk(chunk_id="a#0", note_id="a", title="T1", text="字" * 200, score=1.0),
        ReportChunk(chunk_id="b#0", note_id="b", title="T2", text="词" * 200, score=0.5),
    ]
    ctx = retriever.format_context(chunks)
    assert 40 <= len(ctx) <= 120
    assert "note_id=a" in ctx


def test_create_retriever_disabled_by_default() -> None:
    config = Configuration()
    assert config.enable_report_rag is False
    assert create_report_retriever_from_config(config) is None


def test_create_retriever_when_enabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_REPORT_RAG", "true")
    monkeypatch.setenv("NOTES_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("RAG_TOP_K", "3")
    config = Configuration.from_env()
    retriever = create_report_retriever_from_config(config)
    assert retriever is not None
    assert retriever.top_k == 3


def test_build_chunks_from_documents() -> None:
    docs = [("id1", "标题", "第一段。\n\n" + ("第二段内容。" * 30))]
    chunks = build_chunks_from_documents(docs, chunk_size=100, chunk_overlap=20)
    assert len(chunks) >= 1
    assert chunks[0].note_id == "id1"
    assert chunks[0].chunk_id.startswith("id1#")


def test_invalidate_forces_reload(tmp_path: Path) -> None:
    workspace = tmp_path / "notes"
    workspace.mkdir()
    (workspace / "only.md").write_text("向量检索 与 RAG 流水线", encoding="utf-8")
    retriever = LexicalReportRetriever(workspace, top_k=1)
    assert retriever.retrieve("RAG 流水线")
    retriever.invalidate()
    (workspace / "only.md").write_text("完全无关的烹饪内容", encoding="utf-8")
    # 重建后旧关键词不应再高分命中（可能空）
    hits = retriever.retrieve("RAG 流水线")
    assert not hits or hits[0].score < 0.5
