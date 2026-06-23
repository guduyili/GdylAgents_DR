"""Run offline regression eval cases against a mocked research pipeline."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from config import Configuration, SearchAPI
from models import SummaryState, TodoItem
from services.final_report_generator import FinalReportGenerator
from services.sync_runner import SyncRunner
from services.task_executor import TaskExecutor


@dataclass
class EvalResult:
    topic: str
    passed: bool
    duration_seconds: float
    failures: list[str]


class FakePlanner:
    def plan_todo_list(self, state: SummaryState) -> list[TodoItem]:
        return [
            TodoItem(
                id=1,
                title=f"研究：{state.research_topic}",
                intent="梳理关键事实",
                query=state.research_topic,
            )
        ]

    def create_fallback_task(self, state: SummaryState) -> TodoItem:
        return TodoItem(id=99, title="兜底", intent="兜底", query=state.research_topic)


class FakeSummarizer:
    def summarize_task(self, state: SummaryState, task: TodoItem, context: str) -> str:
        return f"关于 {task.title} 的摘要：{context[:80]}"


class FakeReporting:
    def generate_report(self, state: SummaryState) -> str:
        lines = [f"# {state.research_topic}", "", "## 任务摘要"]
        for task in state.todo_items:
            lines.append(f"### {task.title}")
            lines.append(task.summary or "暂无摘要")
        lines.extend(["", "## 参考", "- https://example.com"])
        return "\n\n".join(lines)


def build_runner(*, research_mode: str) -> SyncRunner:
    config = Configuration(
        search_api=SearchAPI.DUCKDUCKGO,
        enable_notes=False,
        research_mode=research_mode,
    )
    def fake_dispatch(query: str, config: Configuration, loop_count: int):
        return (
            {"results": [{"title": "A", "url": "https://example.com", "content": "body"}]},
            [],
            None,
            "duckduckgo",
        )

    task_executor = TaskExecutor(
        config=config,
        summarizer=FakeSummarizer(),
        state_lock=Lock(),
        drain_tool_events=lambda state, step=None: [],
        search_dispatcher=fake_dispatch,
        context_preparer=lambda search_result, answer_text, config: ("来源 A", "上下文"),
    )
    final_report_generator = FinalReportGenerator(reporting=FakeReporting())

    return SyncRunner(
        planner=FakePlanner(),
        task_executor=task_executor,
        final_report_generator=final_report_generator,
        drain_tool_events=lambda state, step=None: [],
        persist_final_report=lambda state, report: None,
        research_mode=research_mode,
    )


def evaluate_case(case: dict) -> EvalResult:
    topic = str(case["topic"])
    mode = str(case.get("mode", "deep"))
    expected_sections = [str(item) for item in case.get("expected_sections", ["#"])]
    max_duration = float(case.get("max_duration_seconds", 60))

    runner = build_runner(research_mode=mode)
    started = time.monotonic()
    failures: list[str] = []

    try:
        result = runner.run(topic)
    except Exception as exc:  # noqa: BLE001 - eval should capture pipeline failures
        return EvalResult(
            topic=topic,
            passed=False,
            duration_seconds=time.monotonic() - started,
            failures=[f"pipeline error: {exc}"],
        )

    duration = time.monotonic() - started
    report = (result.report_markdown or result.running_summary or "").strip()

    if not report:
        failures.append("empty report")
    for section in expected_sections:
        if section not in report:
            failures.append(f"missing section marker: {section}")

    failed_tasks = [task for task in result.todo_items if task.status == "failed"]
    if failed_tasks:
        failures.append(f"{len(failed_tasks)} task(s) failed")

    if duration > max_duration:
        failures.append(f"duration {duration:.2f}s exceeds {max_duration:.2f}s")

    return EvalResult(
        topic=topic,
        passed=not failures,
        duration_seconds=duration,
        failures=failures,
    )


def load_cases(path: Path) -> list[dict]:
    cases: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            cases.append(json.loads(stripped))
    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run offline research regression evals")
    parser.add_argument(
        "--cases",
        default=str(Path(__file__).with_name("cases.jsonl")),
        help="Path to cases.jsonl",
    )
    parser.add_argument("--quick", action="store_true", help="Only run cases with mode=quick")
    args = parser.parse_args(argv)

    cases = load_cases(Path(args.cases))
    if args.quick:
        cases = [case for case in cases if case.get("mode") == "quick"]

    if not cases:
        print("No eval cases to run", file=sys.stderr)
        return 1

    all_passed = True
    for case in cases:
        result = evaluate_case(case)
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.topic} ({result.duration_seconds:.2f}s)")
        for failure in result.failures:
            print(f"  - {failure}")
        all_passed = all_passed and result.passed

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())