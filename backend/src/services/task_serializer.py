"""任务序列化：将后端 TodoItem 转为前端事件 payload。"""

from __future__ import annotations

from typing import Any

from models import TodoItem


def serialize_task(task: TodoItem) -> dict[str, Any]:
    """将 TodoItem 转为可 JSON 序列化的前端 payload。"""
    return {
        "id": task.id,
        "title": task.title,
        "intent": task.intent,
        "status": task.status,
        "summary": task.summary,
        "sources_summary": task.sources_summary,
        "notices": task.notices,
        "note_id": task.note_id,
        "note_path": task.note_path,
        "stream_token": task.stream_token,
    }
