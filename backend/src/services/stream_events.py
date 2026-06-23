"""Strongly typed SSE stream event contracts for research runs."""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class BaseStreamEvent(BaseModel):
    """Common observability fields attached to every public SSE event."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    timestamp: str
    step: int | None = None
    task_id: int | None = None
    task_run_id: str | None = None
    stream_token: str | None = None
    source: str | None = None
    duration_ms: int | None = None


class StatusEvent(BaseStreamEvent):
    type: Literal["status"] = "status"
    message: str


class TodoTaskEventItem(BaseModel):
    """Serialized todo task payload sent in todo_list events."""

    model_config = ConfigDict(extra="allow")

    id: int | None = None
    title: str
    intent: str
    status: str | None = None
    summary: str | None = None
    sources_summary: str | None = None
    notices: list[str] | None = None
    note_id: str | None = None
    note_path: str | None = None
    task_run_id: str | None = None
    stream_token: str | None = None


class TodoListEvent(BaseStreamEvent):
    type: Literal["todo_list"] = "todo_list"
    tasks: list[TodoTaskEventItem]


class SourcesEvent(BaseStreamEvent):
    type: Literal["sources"] = "sources"
    latest_sources: str
    raw_context: str | None = None
    backend: str | None = None
    note_id: str | None = None
    note_path: str | None = None


class TaskSummaryChunkEvent(BaseStreamEvent):
    type: Literal["task_summary_chunk"] = "task_summary_chunk"
    content: str
    note_id: str | None = None


class TaskStatusEvent(BaseStreamEvent):
    type: Literal["task_status"] = "task_status"
    status: Literal["pending", "in_progress", "completed", "skipped", "failed"]
    title: str | None = None
    intent: str | None = None
    summary: str | None = None
    sources_summary: str | None = None
    error: str | None = None
    note_id: str | None = None
    note_path: str | None = None


class ToolCallEvent(BaseStreamEvent):
    type: Literal["tool_call"] = "tool_call"
    event_id: int | str
    agent: str | None = None
    tool: str
    parameters: dict[str, Any] | list[Any] | str | None = None
    result: Any = None
    input_preview: str | None = None
    output_preview: str | None = None
    note_id: str | None = None
    note_path: str | None = None


class PhaseDurationEvent(BaseStreamEvent):
    type: Literal["phase_duration"] = "phase_duration"
    phase: Literal["planning", "search", "summary", "report", "total"]


class ReportNoteEvent(BaseStreamEvent):
    type: Literal["report_note"] = "report_note"
    note_id: str
    title: str | None = None
    content: str | None = None
    note_path: str | None = None


class FinalReportEvent(BaseStreamEvent):
    type: Literal["final_report"] = "final_report"
    report: str
    note_id: str | None = None
    note_path: str | None = None


class ReviewResultEvent(BaseStreamEvent):
    type: Literal["review_result"] = "review_result"
    passed: bool
    score: int = Field(ge=0, le=100)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class FactCheckResultEvent(BaseStreamEvent):
    type: Literal["fact_check_result"] = "fact_check_result"
    passed: bool
    score: int = Field(ge=0, le=100)
    matched_sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_terms: list[str] = Field(default_factory=list)


class SkillLoadedEvent(BaseStreamEvent):
    type: Literal["skill_loaded"] = "skill_loaded"
    skill_name: str
    skill_description: str | None = None
    preview: str | None = None


class DoneEvent(BaseStreamEvent):
    type: Literal["done"] = "done"


class ErrorEvent(BaseStreamEvent):
    type: Literal["error"] = "error"
    detail: str


PublicStreamEvent: TypeAlias = (
    StatusEvent
    | TodoListEvent
    | SourcesEvent
    | TaskSummaryChunkEvent
    | TaskStatusEvent
    | ToolCallEvent
    | ReportNoteEvent
    | FinalReportEvent
    | ReviewResultEvent
    | FactCheckResultEvent
    | SkillLoadedEvent
    | PhaseDurationEvent
    | DoneEvent
    | ErrorEvent
)

_STREAM_EVENT_ADAPTER = TypeAdapter(PublicStreamEvent)

_DRAFT_RUN_ID = "__draft__"
_DRAFT_TIMESTAMP = "__draft__"


def build_stream_event(event: dict[str, Any]) -> dict[str, Any]:
    """Validate a partial SSE payload against the public event contract.

    ``run_id`` and ``timestamp`` are injected with placeholders for validation,
    then removed so callers can enrich events later via ``normalize_stream_event``.
    """
    payload = dict(event)
    payload.setdefault("run_id", _DRAFT_RUN_ID)
    payload.setdefault("timestamp", _DRAFT_TIMESTAMP)
    validated = _STREAM_EVENT_ADAPTER.validate_python(payload)
    result = validated.model_dump(exclude_none=True)
    if result.get("run_id") == _DRAFT_RUN_ID:
        result.pop("run_id", None)
    if result.get("timestamp") == _DRAFT_TIMESTAMP:
        result.pop("timestamp", None)
    return result


def normalize_stream_event(event: dict[str, Any], *, run_id: str, timestamp: str) -> dict[str, Any]:
    """Attach observability fields and validate public stream events.

    ``__task_done__`` is an internal queue sentinel, not part of the public SSE
    protocol. It keeps the same observability enrichment for existing runner
    logic but intentionally bypasses public-event validation.
    """
    payload = dict(event)
    payload.setdefault("run_id", run_id)
    payload.setdefault("timestamp", timestamp)

    if payload.get("type") == "__task_done__":
        return payload

    validated = _STREAM_EVENT_ADAPTER.validate_python(payload)
    return validated.model_dump(exclude_none=True)
