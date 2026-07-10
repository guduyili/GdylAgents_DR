"""Run cancellation registry: in-memory and Redis pub/sub broadcast."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Event, Lock, Thread
from typing import Protocol

from services.active_run_registry import ActiveRunRegistry

logger = logging.getLogger(__name__)

DEFAULT_REDIS_CANCEL_CHANNEL = "research:runs:cancel"


@dataclass(frozen=True)
class CancelRequestResult:
    """Outcome of a run cancellation request."""

    local_cancelled: bool
    broadcast_sent: bool

    @property
    def acknowledged(self) -> bool:
        return self.local_cancelled or self.broadcast_sent


class RunCancellationRegistry(Protocol):
    """Track active runs and propagate cancel signals across workers."""

    def register(self, run_id: str, stop_event: Event) -> None: ...

    def unregister(self, run_id: str) -> None: ...

    def request_cancel(self, run_id: str) -> CancelRequestResult: ...

    def is_active(self, run_id: str) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


class MemoryRunCancellationRegistry:
    """Process-local cancellation registry (single worker)."""

    def __init__(self) -> None:
        self._local = ActiveRunRegistry()

    def register(self, run_id: str, stop_event: Event) -> None:
        self._local.register(run_id, stop_event)

    def unregister(self, run_id: str) -> None:
        self._local.unregister(run_id)

    def request_cancel(self, run_id: str) -> CancelRequestResult:
        local_cancelled = self._local.request_cancel(run_id)
        return CancelRequestResult(local_cancelled=local_cancelled, broadcast_sent=False)

    def is_active(self, run_id: str) -> bool:
        return self._local.is_active(run_id)

    def start(self) -> None:
        return

    def stop(self) -> None:
        return


class RedisRunCancellationRegistry:
    """Local registry plus Redis pub/sub cancel broadcast for multi-worker deployments."""

    def __init__(
        self,
        redis_url: str,
        *,
        channel: str = DEFAULT_REDIS_CANCEL_CHANNEL,
    ) -> None:
        try:
            import redis
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "CANCEL_BROADCAST_BACKEND=redis 需要安装 redis 依赖：uv sync --extra redis"
            ) from exc

        self._local = ActiveRunRegistry()
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._channel = channel
        self._listener_stop = Event()
        self._listener_thread: Thread | None = None
        self._lock = Lock()

    def register(self, run_id: str, stop_event: Event) -> None:
        self._local.register(run_id, stop_event)

    def unregister(self, run_id: str) -> None:
        self._local.unregister(run_id)

    def request_cancel(self, run_id: str) -> CancelRequestResult:
        local_cancelled = self._local.request_cancel(run_id)
        receivers = int(self._redis.publish(self._channel, run_id))
        broadcast_sent = receivers > 0 or not local_cancelled
        return CancelRequestResult(
            local_cancelled=local_cancelled,
            broadcast_sent=broadcast_sent,
        )

    def is_active(self, run_id: str) -> bool:
        return self._local.is_active(run_id)

    def start(self) -> None:
        with self._lock:
            if self._listener_thread and self._listener_thread.is_alive():
                return
            self._listener_stop.clear()
            self._listener_thread = Thread(
                target=self._listen_for_cancel_messages,
                name="redis-cancel-listener",
                daemon=True,
            )
            self._listener_thread.start()
            logger.info("Redis 取消广播监听已启动: channel=%s", self._channel)

    def stop(self) -> None:
        self._listener_stop.set()
        with self._lock:
            thread = self._listener_thread
        if thread and thread.is_alive():
            thread.join(timeout=2)
        logger.info("Redis 取消广播监听已停止")

    def _listen_for_cancel_messages(self) -> None:
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(self._channel)
        try:
            while not self._listener_stop.is_set():
                message = pubsub.get_message(timeout=0.5)
                if not message or message.get("type") != "message":
                    continue
                run_id = str(message.get("data", "")).strip()
                if not run_id:
                    continue
                if self._local.request_cancel(run_id):
                    logger.info("收到 Redis 取消广播并已停止本进程 run: run_id=%s", run_id)
        finally:
            pubsub.close()


def create_run_cancellation_registry(
    *,
    backend: str,
    redis_url: str | None = None,
    redis_cancel_channel: str = DEFAULT_REDIS_CANCEL_CHANNEL,
) -> RunCancellationRegistry:
    """Create the configured cancellation registry implementation."""
    normalized = (backend or "memory").strip().lower()
    if normalized == "redis":
        if not redis_url:
            raise ValueError("CANCEL_BROADCAST_BACKEND=redis 时必须设置 REDIS_URL")
        return RedisRunCancellationRegistry(redis_url, channel=redis_cancel_channel)
    if normalized == "memory":
        return MemoryRunCancellationRegistry()
    raise ValueError(f"不支持的 CANCEL_BROADCAST_BACKEND: {backend}")