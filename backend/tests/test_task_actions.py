import pytest
from pydantic import ValidationError

from services.task_actions import FinishAction, SearchAction, parse_task_action


@pytest.mark.parametrize(
    "payload, expected_type, expected",
    [
        ({"action": "search", "query": "  Agent 工具调用 \n", "reason": " 补充来源 "},
         SearchAction, {"action": "search", "query": "Agent 工具调用", "reason": "补充来源"}),
        ({"action": "finish", "reason": "  已有足够证据 \n"},
         FinishAction, {"action": "finish", "reason": "已有足够证据"}),
        ({"action": "search", "query": "中" * 512, "reason": "a" * 512},
         SearchAction, {"action": "search", "query": "中" * 512, "reason": "a" * 512}),
        ({"action": "finish", "reason": "a" * 512},
         FinishAction, {"action": "finish", "reason": "a" * 512}),
    ],
)
def test_parse_action_normalizes_valid_payload_without_mutating_input(payload, expected_type, expected):
    original = dict(payload)
    action = parse_task_action(payload)
    assert isinstance(action, expected_type)
    assert action.model_dump() == expected
    assert payload == original
    with pytest.raises(ValidationError):
        action.reason = "changed"


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "shell", "reason": "run command"},
        {"action": "SEARCH", "query": "agent", "reason": "search"},
        {"query": "agent", "reason": "missing action"},
        {"action": "search", "reason": "missing query"},
        {"action": "search", "query": "agent"},
        {"action": "finish"},
        {"action": "search", "query": " \t\n", "reason": "search"},
        {"action": "finish", "reason": " \t\n"},
        {"action": "search", "query": "a" * 513, "reason": "search"},
        {"action": "finish", "reason": "a" * 513},
        {"action": "search", "query": 123, "reason": "search"},
        {"action": "finish", "reason": True},
        {"action": "search", "query": None, "reason": "search"},
        {"action": "finish", "reason": "done", "query": "hidden search"},
        {"action": "search", "query": "agent", "reason": "search", "tool": "shell"},
        [{"action": "finish", "reason": "done"}],
        '{"action":"finish","reason":"done"}',
        None,
    ],
)
def test_parse_action_rejects_invalid_or_ambiguous_payload(payload):
    with pytest.raises(ValidationError):
        parse_task_action(payload)
