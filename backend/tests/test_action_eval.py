from pathlib import Path

from evals.action_eval import compare_case, load_action_cases, main, run_case


def case(**overrides):
    value = {
        "id": "rewrite-empty",
        "topic": "Agent",
        "initial_query": "agent",
        "materials": {
            "agent": [],
            "agent tools": [
                {"title": "Tools", "url": "https://example.com/tools", "content": "tool evidence"}
            ],
        },
        "decisions": [
            {"action": "search", "query": "agent", "reason": "collect"},
            {"action": "search", "query": "agent tools", "reason": "rewrite"},
            {"action": "finish", "reason": "enough"},
        ],
        "expected_stop_reason": "finish",
        "minimum_sources": 1,
    }
    value.update(overrides)
    return value


def test_action_eval_compares_same_materials_and_reports_gain():
    result = compare_case(case())

    assert result.fixed.search_count == 1
    assert result.fixed.unique_sources == 0
    assert result.decision.search_count == 2
    assert result.decision.unique_sources == 1
    assert result.decision.stop_reason == "finish"
    assert result.passed is True
    assert result.source_gain == 1


def test_action_eval_scores_claim_coverage_and_conflicting_sources():
    result = compare_case(case(
        id="conflict-and-claim",
        materials={
            "agent": [{"url": "https://example.com/old", "title": "Old", "content": "old"}],
            "agent tools": [
                {"url": "https://example.com/old", "title": "Old", "content": "old"},
                {"url": "https://example.com/new", "title": "New", "content": "new"},
            ],
        },
        claims=[{"id": "new-fact", "required_urls": ["https://example.com/new"]}],
        conflict_groups=[["https://example.com/old", "https://example.com/new"]],
    ))

    assert result.fixed.claim_coverage == 0.0
    assert result.decision.claim_coverage == 1.0
    assert result.decision.conflict_groups == 1
    assert result.claim_coverage_gain == 1.0


def test_action_eval_records_insufficient_evidence_without_inflating_coverage():
    result = run_case(case(
        id="insufficient",
        decisions=[{"action": "finish", "reason": "not enough"}],
        claims=[{"id": "missing", "required_urls": ["https://example.com/missing"]}],
        expected_stop_reason="no_evidence", minimum_sources=0,
    ))

    assert result.passed is True
    assert result.decision.claim_coverage == 0.0
    assert result.decision.conflict_groups == 0


def test_action_eval_preserves_safety_stops_and_never_retries_repeat():
    result = run_case(case(
        id="repeat",
        decisions=[
            {"action": "search", "query": "agent", "reason": "collect"},
            {"action": "search", "query": " AGENT ", "reason": "repeat"},
        ], expected_stop_reason="repeated_query", minimum_sources=0,
    ))

    assert result.decision.search_count == 1
    assert result.decision.stop_reason == "repeated_query"
    assert result.passed is True


def test_action_eval_invalid_action_has_zero_searches():
    result = run_case(case(
        id="invalid",
        decisions=[{"action": "shell", "reason": "unsafe"}],
        expected_stop_reason="invalid_action", minimum_sources=0,
    ))

    assert result.decision.search_count == 0
    assert result.decision.stop_reason == "invalid_action"
    assert result.passed is True


def test_action_eval_load_and_cli(tmp_path: Path, capsys):
    path = tmp_path / "actions.jsonl"
    path.write_text('{"id":"case","topic":"A","initial_query":"a","materials":{"a":[]},'
                    '"decisions":[{"action":"finish","reason":"none"}],'
                    '"expected_stop_reason":"no_evidence","minimum_sources":0}\n', encoding="utf-8")
    assert load_action_cases(path)[0]["id"] == "case"
    assert main(["--cases", str(path)]) == 0
    assert "case" in capsys.readouterr().out
