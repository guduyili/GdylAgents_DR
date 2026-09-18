"""Bounded single-task search/observe/finish loop, independent of model SDKs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from time import monotonic
from typing import Callable, Generator
from unicodedata import normalize
from urllib.parse import urlsplit

from pydantic import ValidationError

from models import TodoItem
from services.cancellation import ResearchCancelled, StopSignal, ensure_not_cancelled
from services.search_backends import SearchOutcome
from services.task_actions import FinishAction, parse_task_action


@dataclass(frozen=True)
class Evidence:
    title: str
    url: str
    content: str
    published_at: str | None = None


@dataclass(frozen=True)
class Observation:
    query: str
    result_count: int
    sources: tuple[Evidence, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class DecisionContext:
    topic: str
    title: str
    intent: str
    initial_query: str
    step: int
    max_steps: int
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class LoopResult:
    outcome: SearchOutcome
    stop_reason: str


class DecisionLoopError(Exception):
    """The loop stopped on an error without usable evidence."""


def _sources(payload: dict) -> tuple[Evidence, ...]:
    """Bound untrusted provider data before exposing it to the decision model."""
    found: dict[str, Evidence] = {}
    entries = payload.get("results", [])
    if not isinstance(entries, list):
        return ()
    for entry in entries[:20]:
        if not isinstance(entry, dict):
            continue
        url = entry.get("url", "")
        if not isinstance(url, str) or len(url) > 2048:
            continue
        url = url.strip()
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                continue
        except ValueError:
            continue
        title, content = entry.get("title"), entry.get("content")
        found.setdefault(url, Evidence(
            title=title[:256] if isinstance(title, str) else url,
            url=url, content=content[:2000] if isinstance(content, str) else "",
            published_at=entry.get("published_at") if isinstance(entry.get("published_at"), str) else None,
        ))
    return tuple(found.values())


class DecisionLoop:
    """All mutable state belongs to one run, allowing concurrent tasks."""

    def __init__(self, *, max_steps: int, timeout_seconds: float, clock=monotonic):
        if not 1 <= max_steps <= 12 or not 0 < timeout_seconds <= 600:
            raise ValueError("Invalid decision loop limits")
        self.max_steps, self.timeout_seconds, self.clock = max_steps, timeout_seconds, clock

    def run(
        self, task: TodoItem, topic: str, *,
        decide: Callable[[DecisionContext, float], object],
        search: Callable[[str, float], SearchOutcome],
        stop_event: StopSignal | None = None,
    ) -> Generator[dict, None, LoopResult]:
        deadline = self.clock() + self.timeout_seconds
        observations: list[Observation] = []
        evidence: dict[str, Evidence] = {}
        queries: set[str] = set()
        notices: list[str] = []
        backend = "decision_loop"
        stop_reason = "step_limit"
        step = 0
        for step in range(1, self.max_steps + 1):
            ensure_not_cancelled(stop_event)
            remaining = deadline - self.clock()
            if remaining <= 0:
                stop_reason = "timeout"
                break
            context = DecisionContext(
                topic=(topic or "")[:1000], title=task.title[:512], intent=task.intent[:1000],
                initial_query=task.query[:512], step=step, max_steps=self.max_steps,
                observations=tuple(observations),
            )
            try:
                action = parse_task_action(decide(context, remaining))
            except ResearchCancelled:
                raise
            except TimeoutError:
                stop_reason = "timeout"
                break
            except (ValidationError, ValueError, TypeError):
                stop_reason = "invalid_action"
                break
            except Exception:
                stop_reason = "decision_error"
                break
            ensure_not_cancelled(stop_event)
            if self.clock() >= deadline:
                stop_reason = "timeout"
                break
            yield {"step": step, **action.model_dump()}
            if isinstance(action, FinishAction):
                stop_reason = "finish" if evidence else "no_evidence"
                break
            key = " ".join(normalize("NFKC", action.query).casefold().split())
            if key in queries:
                stop_reason = "repeated_query"
                break
            queries.add(key)
            ensure_not_cancelled(stop_event)
            remaining = deadline - self.clock()
            if remaining <= 0:
                stop_reason = "timeout"
                break
            try:
                outcome = search(action.query, remaining)
                ensure_not_cancelled(stop_event)
                if self.clock() >= deadline:
                    stop_reason = "timeout"
                    break
                sources = _sources(outcome.payload)
                for source in sources:
                    if len(evidence) < 20:
                        evidence.setdefault(source.url, source)
                backend = outcome.backend_label
                notices.extend(str(item)[:512] for item in outcome.notices[:3])
                observation = Observation(action.query, len(sources), sources[:5])
            except ResearchCancelled:
                raise
            except TimeoutError:
                stop_reason = "timeout"
                break
            except Exception as exc:
                ensure_not_cancelled(stop_event)
                observation = Observation(action.query, 0, error=type(exc).__name__)
            observations.append(observation)
            yield {"step": step, "action": "observation", "query": action.query,
                   "result_count": observation.result_count, "error": observation.error}
        ensure_not_cancelled(stop_event)
        notices.append(f"决策循环结束：{stop_reason}（{step}/{self.max_steps} 步）")
        yield {"step": step, "action": "stop", "stop_reason": stop_reason}
        return LoopResult(SearchOutcome(
            {"results": [asdict(item) for item in evidence.values()], "backend": backend},
            notices, None, backend,
        ), stop_reason)
