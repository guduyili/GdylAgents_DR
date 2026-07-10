from __future__ import annotations

from threading import Event
from unittest.mock import MagicMock, patch

import pytest

from services.run_cancellation_registry import (
    CancelRequestResult,
    MemoryRunCancellationRegistry,
    RedisRunCancellationRegistry,
    create_run_cancellation_registry,
)


def test_create_run_cancellation_registry_memory() -> None:
    registry = create_run_cancellation_registry(backend="memory")
    assert isinstance(registry, MemoryRunCancellationRegistry)


def test_create_run_cancellation_registry_redis_requires_url() -> None:
    with pytest.raises(ValueError, match="REDIS_URL"):
        create_run_cancellation_registry(backend="redis", redis_url=None)


@patch("redis.Redis")
def test_redis_registry_publishes_cancel_message(mock_redis_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client.publish.return_value = 0
    mock_redis_cls.from_url.return_value = mock_client

    registry = RedisRunCancellationRegistry("redis://localhost:6379/0", channel="test:cancel")
    result = registry.request_cancel("run-abc")

    mock_client.publish.assert_called_once_with("test:cancel", "run-abc")
    assert result == CancelRequestResult(local_cancelled=False, broadcast_sent=True)


@patch("redis.Redis")
def test_redis_registry_local_cancel_skips_broadcast_ack(mock_redis_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client.publish.return_value = 1
    mock_redis_cls.from_url.return_value = mock_client

    registry = RedisRunCancellationRegistry("redis://localhost:6379/0")
    stop_event = Event()
    registry.register("run-local", stop_event)

    result = registry.request_cancel("run-local")

    assert result.local_cancelled is True
    assert result.broadcast_sent is True
    assert stop_event.is_set()


@patch("redis.Redis")
def test_redis_registry_listener_triggers_local_cancel(mock_redis_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_pubsub = MagicMock()
    mock_client.pubsub.return_value = mock_pubsub
    mock_redis_cls.from_url.return_value = mock_client

    registry = RedisRunCancellationRegistry("redis://localhost:6379/0", channel="test:cancel")
    stop_event = Event()
    registry.register("run-remote", stop_event)

    messages = iter([{"type": "message", "data": "run-remote"}])

    def get_message_side_effect(*_args, **_kwargs):
        try:
            return next(messages)
        except StopIteration:
            registry._listener_stop.set()
            return None

    mock_pubsub.get_message.side_effect = get_message_side_effect

    registry._listen_for_cancel_messages()

    assert stop_event.is_set()
    mock_pubsub.subscribe.assert_called_once_with("test:cancel")
    mock_pubsub.close.assert_called_once()