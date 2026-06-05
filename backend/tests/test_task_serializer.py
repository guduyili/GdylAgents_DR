from __future__ import annotations

from models import TodoItem
from services.task_serializer import serialize_task


def test_serialize_task_returns_frontend_payload() -> None:
    task = TodoItem(
        id=1,
        title="任务一",
        intent="研究",
        query="agent",
        status="completed",
        summary="摘要",
        sources_summary="来源",
        notices=["提示"],
        note_id="note_1",
        note_path="/tmp/note.md",
        stream_token="task_1",
    )

    assert serialize_task(task) == {
        "id": 1,
        "title": "任务一",
        "intent": "研究",
        "status": "completed",
        "summary": "摘要",
        "sources_summary": "来源",
        "notices": ["提示"],
        "note_id": "note_1",
        "note_path": "/tmp/note.md",
        "stream_token": "task_1",
    }
