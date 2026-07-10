"""研究运行记录存储：内存/SQLite 实现，用于查询某次研究的时间线。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Protocol


class ResearchRunStore(Protocol):
    """记录和查询研究运行事件的抽象接口。"""

    def start_run(self, *, run_id: str, topic: str) -> None: ...
    def record_event(self, run_id: str, event: dict[str, Any]) -> None: ...
    def complete_run(self, run_id: str, *, phase_durations: dict[str, int] | None = None) -> None: ...
    def cancel_run(self, run_id: str, *, phase_durations: dict[str, int] | None = None) -> None: ...
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

    def complete_run(self, run_id: str, *, phase_durations: dict[str, int] | None = None) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                run["status"] = "completed"
                if phase_durations is not None:
                    run["phase_durations"] = dict(phase_durations)

    def cancel_run(self, run_id: str, *, phase_durations: dict[str, int] | None = None) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                run["status"] = "cancelled"
                if phase_durations is not None:
                    run["phase_durations"] = dict(phase_durations)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            snapshot = dict(run)
            snapshot["events"] = list(run["events"])
            if "phase_durations" in run:
                snapshot["phase_durations"] = dict(run["phase_durations"])
            return snapshot

    def _evict_if_needed(self) -> None:
        """当存储超过上限时，淘汰最早的运行。"""
        while len(self._runs) > self._max_runs:
            oldest_key = next(iter(self._runs))
            del self._runs[oldest_key]


class SQLiteResearchRunStore:
    """SQLite 实现：持久化研究运行和事件，服务重启后仍可查询。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._init_schema()

    def start_run(self, *, run_id: str, topic: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM research_events WHERE run_id = ?", (run_id,))
            conn.execute(
                """
                INSERT INTO research_runs (run_id, topic, status)
                VALUES (?, ?, 'running')
                ON CONFLICT(run_id) DO UPDATE SET
                    topic = excluded.topic,
                    status = 'running'
                """,
                (run_id, topic),
            )

    def record_event(self, run_id: str, event: dict[str, Any]) -> None:
        payload_json = json.dumps(event, ensure_ascii=False)
        event_type = str(event.get("type", ""))
        timestamp = event.get("timestamp")
        with self._lock, self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM research_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if exists is None:
                return
            conn.execute(
                """
                INSERT INTO research_events (run_id, event_type, timestamp, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, event_type, timestamp, payload_json),
            )

    def complete_run(self, run_id: str, *, phase_durations: dict[str, int] | None = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE research_runs SET status = 'completed' WHERE run_id = ?",
                (run_id,),
            )
            if phase_durations is not None:
                conn.execute(
                    """
                    UPDATE research_runs
                    SET phase_durations_json = ?
                    WHERE run_id = ?
                    """,
                    (json.dumps(phase_durations, ensure_ascii=False), run_id),
                )

    def cancel_run(self, run_id: str, *, phase_durations: dict[str, int] | None = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE research_runs SET status = 'cancelled' WHERE run_id = ?",
                (run_id,),
            )
            if phase_durations is not None:
                conn.execute(
                    """
                    UPDATE research_runs
                    SET phase_durations_json = ?
                    WHERE run_id = ?
                    """,
                    (json.dumps(phase_durations, ensure_ascii=False), run_id),
                )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            run = conn.execute(
                "SELECT run_id, topic, status, phase_durations_json FROM research_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                return None
            events = conn.execute(
                """
                SELECT payload_json
                FROM research_events
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()
        snapshot: dict[str, Any] = {
            "run_id": run["run_id"],
            "topic": run["topic"],
            "status": run["status"],
            "events": [json.loads(row["payload_json"]) for row in events],
        }
        phase_json = run["phase_durations_json"]
        if phase_json:
            snapshot["phase_durations"] = json.loads(phase_json)
        return snapshot

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_runs (
                    run_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    status TEXT NOT NULL,
                    phase_durations_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TEXT,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES research_runs(run_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_research_events_run_id ON research_events(run_id)"
            )
            try:
                conn.execute(
                    "ALTER TABLE research_runs ADD COLUMN phase_durations_json TEXT"
                )
            except sqlite3.OperationalError:
                pass

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
