"""研究运行记录存储：内存实现，用于查询某次研究的时间线。"""

from __future__ import annotations

from threading import Lock
from typing import Any, Protocol


class ResearchRunStore(Protocol):
    """记录和查询研究运行事件的抽象接口。"""

    def start_run(self, *, run_id: str, topic: str) -> None: ...
    def record_event(self, run_id: str, event: dict[str, Any]) -> None: ...
    def complete_run(self, run_id: str) -> None: ...
    def get_run(self, run_id: str) -> dict[str, Any] | None: ...


class InMemoryResearchRunStore:
    """内存实现：存储最近 N 次研究运行的完整时间线，线程安全。"""

    def __init__(self, max_runs: int = 100) -> None:
        self._max_runs = max_runs
        self._runs: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def start_run(self, *, run_id: str, topic: str) -> None:
        with self._lock:
            self._runs[run_id] = {
                "run_id": run_id,
                "topic": topic,
                "status": "running",
                "events": [],
            }
            self._evict_if_needed()

    def record_event(self, run_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                run["events"].append(event)

    def complete_run(self, run_id: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                run["status"] = "completed"

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            return dict(run)

    def _evict_if_needed(self) -> None:
        """当存储超过上限时，淘汰最早的已完成运行。"""
        while len(self._runs) > self._max_runs:
            oldest_key = next(iter(self._runs))
            del self._runs[oldest_key]