"""Deterministic action-level evaluation for fixed versus decision search.

The evaluator never calls a network or an LLM. It replays a decision sequence
against the same material map, making regressions in loop safety measurable.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
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
    claim_coverage: float
    conflict_groups: int
    evidence_support: float
    freshness_coverage: float
    summary_correctness: float


@dataclass(frozen=True)
class ActionEvalResult:
    case_id: str
    fixed: ModeMetrics
    decision: ModeMetrics
    source_gain: int
    claim_coverage_gain: float
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


def _quality_metrics(results: object, case: dict) -> tuple[float, int]:
    urls = _valid_urls(results)
    claims = case.get("claims", [])
    covered = 0
    if isinstance(claims, list):
        for claim in claims:
            required = claim.get("required_urls", []) if isinstance(claim, dict) else []
            if isinstance(required, list) and required and all(item in urls for item in required):
                covered += 1
    coverage = covered / len(claims) if isinstance(claims, list) and claims else 0.0
    conflicts = 0
    groups = case.get("conflict_groups", [])
    if isinstance(groups, list):
        for group in groups:
            if isinstance(group, list) and len(set(group) & urls) >= 2:
                conflicts += 1
    return coverage, conflicts


def _evidence_quality(results: object, case: dict, summary: str = "") -> tuple[float, float, float]:
    """Score marked claims from source snippets, dates and optional summary text."""
    entries = [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []
    by_url = {item.get("url"): item for item in entries if item.get("url") in _valid_urls(entries)}
    claims = case.get("claims", [])
    supported = 0
    freshness_required = 0
    fresh = 0
    as_of_raw = case.get("as_of")
    try:
        as_of = date.fromisoformat(str(as_of_raw)[:10])
    except ValueError:
        as_of = None
    if isinstance(claims, list):
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            urls = claim.get("required_urls", [])
            sources = [by_url[url] for url in urls if isinstance(urls, list) and url in by_url]
            terms = claim.get("required_terms", [])
            combined = " ".join(
                str(source.get("title", "")) + " " + str(source.get("content", ""))
                for source in sources
            ).casefold()
            if sources and (not terms or all(str(term).casefold() in combined for term in terms)):
                supported += 1
            max_age = claim.get("max_age_days")
            if max_age is not None:
                freshness_required += 1
                if as_of is not None and sources:
                    dates: list[date] = []
                    for source in sources:
                        try:
                            dates.append(date.fromisoformat(str(source.get("published_at", ""))[:10]))
                        except ValueError:
                            pass
                    if dates and all(0 <= (as_of - published).days <= int(max_age) for published in dates):
                        fresh += 1
    denominator = len(claims) if isinstance(claims, list) and claims else 0
    evidence_support = supported / denominator if denominator else 0.0
    freshness_coverage = fresh / freshness_required if freshness_required else 0.0
    summary_terms = case.get("summary_required_terms", [])
    if isinstance(summary_terms, list) and summary_terms:
        summary_text = str(summary).casefold()
        summary_correctness = sum(str(term).casefold() in summary_text for term in summary_terms) / len(summary_terms)
    else:
        summary_correctness = 0.0
    return evidence_support, freshness_coverage, summary_correctness


def _mode_metrics(results: object, case: dict, *, search_count: int, stop_reason: str, errors: int, summary: str = "") -> ModeMetrics:
    coverage, conflicts = _quality_metrics(results, case)
    support, freshness, summary_correctness = _evidence_quality(results, case, summary)
    return ModeMetrics(
        search_count, len(_valid_urls(results)), stop_reason, errors,
        coverage, conflicts, support, freshness, summary_correctness,
    )


def _fixed_metrics(case: dict) -> ModeMetrics:
    outcome = _material_result(case.get("materials", {}), str(case.get("initial_query", "")))
    summaries = case.get("summaries", {})
    summary = summaries.get("fixed", "") if isinstance(summaries, dict) else ""
    return _mode_metrics(outcome.payload.get("results"), case, search_count=1, stop_reason="fixed", errors=0, summary=summary)


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

    summaries = case.get("summaries", {})
    summary = summaries.get("decision", "") if isinstance(summaries, dict) else ""
    decision = _mode_metrics(
        result.outcome.payload.get("results"), case, search_count=searches,
        stop_reason=result.stop_reason, errors=errors, summary=summary,
    )
    fixed = _fixed_metrics(case)
    expected_reason = str(case.get("expected_stop_reason", "finish"))
    minimum_sources = int(case.get("minimum_sources", 0))
    minimum_support = float(case.get("minimum_evidence_support", 0.0))
    failures: list[str] = []
    if decision.stop_reason != expected_reason:
        failures.append(f"stop reason {decision.stop_reason!r} != {expected_reason!r}")
    if decision.unique_sources < minimum_sources:
        failures.append(f"sources {decision.unique_sources} < {minimum_sources}")
    if decision.evidence_support < minimum_support:
        failures.append(f"evidence support {decision.evidence_support:.2f} < {minimum_support:.2f}")
    return ActionEvalResult(
        case_id=str(case.get("id", case.get("topic", "case"))), fixed=fixed,
        decision=decision, source_gain=decision.unique_sources - fixed.unique_sources,
        claim_coverage_gain=decision.claim_coverage - fixed.claim_coverage,
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
