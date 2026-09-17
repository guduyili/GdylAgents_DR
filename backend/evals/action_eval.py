"""Deterministic action-level evaluation for fixed versus decision search.

The evaluator never calls a network or an LLM. It replays a decision sequence
against the same material map, making regressions in loop safety measurable.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

from models import TodoItem
from services.decision_loop import DecisionLoop
from services.search_backends import SearchOutcome


@dataclass(frozen=True)
class ModeMetrics:
    search_count: int
    unique_sources: int
    stop_reason: str
    errors: int


@dataclass(frozen=True)
class ActionEvalResult:
    case_id: str
    fixed: ModeMetrics
    decision: ModeMetrics
    source_gain: int
    passed: bool
    failures: tuple[str, ...]


def _valid_urls(results: object) -> set[str]:
    urls: set[str] = set()
    if not isinstance(results, list):
        return urls
    for item in results:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str):
            continue
        try:
            parsed = urlsplit(url.strip())
        except ValueError:
            continue
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            urls.add(url.strip())
    return urls


def _material_result(materials: dict, query: str) -> SearchOutcome:
    entries = materials.get(query, [])
    if not isinstance(entries, list):
        entries = []
    return SearchOutcome(
        payload={"results": [dict(item) for item in entries if isinstance(item, dict)]},
        notices=[], answer_text=None, backend_label="offline-material",
    )


def _fixed_metrics(case: dict) -> ModeMetrics:
    outcome = _material_result(case.get("materials", {}), str(case.get("initial_query", "")))
    return ModeMetrics(1, len(_valid_urls(outcome.payload.get("results"))), "fixed", 0)


def run_case(case: dict) -> ActionEvalResult:
    """Replay one case and return comparable metrics for both modes."""
    materials = case.get("materials", {})
    decisions = iter(case.get("decisions", []))
    searches = 0
    errors = 0

    def decide(_context, _remaining):
        return next(decisions)

    def search(query, _remaining):
        nonlocal searches, errors
        searches += 1
        try:
            return _material_result(materials, query)
        except Exception:
            errors += 1
            raise

    task = TodoItem(
        id=1, title=str(case.get("topic", "case")),
        intent="offline action evaluation", query=str(case.get("initial_query", "")),
    )
    loop = DecisionLoop(
        max_steps=int(case.get("max_steps", 6)),
        timeout_seconds=float(case.get("timeout_seconds", 30)),
    ).run(task, str(case.get("topic", "")), decide=decide, search=search)
    try:
        while True:
            next(loop)
    except StopIteration as done:
        result = done.value

    decision = ModeMetrics(
        search_count=searches,
        unique_sources=len(_valid_urls(result.outcome.payload.get("results"))),
        stop_reason=result.stop_reason,
        errors=errors,
    )
    fixed = _fixed_metrics(case)
    expected_reason = str(case.get("expected_stop_reason", "finish"))
    minimum_sources = int(case.get("minimum_sources", 0))
    failures: list[str] = []
    if decision.stop_reason != expected_reason:
        failures.append(f"stop reason {decision.stop_reason!r} != {expected_reason!r}")
    if decision.unique_sources < minimum_sources:
        failures.append(f"sources {decision.unique_sources} < {minimum_sources}")
    return ActionEvalResult(
        case_id=str(case.get("id", case.get("topic", "case"))), fixed=fixed,
        decision=decision, source_gain=decision.unique_sources - fixed.unique_sources,
        passed=not failures, failures=tuple(failures),
    )


def compare_case(case: dict) -> ActionEvalResult:
    """Alias emphasizing that both modes use the same offline materials."""
    return run_case(case)


def load_action_cases(path: Path) -> list[dict]:
    cases: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))
    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic action-level evaluations")
    parser.add_argument("--cases", default=str(Path(__file__).with_name("action_cases.jsonl")))
    args = parser.parse_args(argv)
    cases = load_action_cases(Path(args.cases))
    if not cases:
        print("No action eval cases to run", file=sys.stderr)
        return 1
    passed = True
    for case in cases:
        result = run_case(case)
        print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
        passed = passed and result.passed
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
