from __future__ import annotations

from pathlib import Path

from evals.run_eval import evaluate_case, load_cases, main


def test_evaluate_quick_case_passes_with_mocked_pipeline() -> None:
    result = evaluate_case(
        {
            "topic": "AI Agent",
            "mode": "quick",
            "expected_sections": ["#", "##"],
            "max_duration_seconds": 30,
        }
    )

    assert result.passed is True
    assert result.failures == []
    assert result.duration_seconds >= 0


def test_load_cases_reads_jsonl(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        '{"topic": "A", "mode": "quick"}\n\n{"topic": "B", "mode": "deep"}\n',
        encoding="utf-8",
    )

    cases = load_cases(cases_path)

    assert len(cases) == 2
    assert cases[0]["topic"] == "A"


def test_main_quick_flag_filters_cases(tmp_path: Path, capsys) -> None:
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        '{"topic": "Quick Topic", "mode": "quick", "expected_sections": ["#"], "max_duration_seconds": 30}\n'
        '{"topic": "Deep Topic", "mode": "deep", "expected_sections": ["#", "参考"], "max_duration_seconds": 30}\n',
        encoding="utf-8",
    )

    exit_code = main(["--cases", str(cases_path), "--quick"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Quick Topic" in output
    assert "Deep Topic" not in output