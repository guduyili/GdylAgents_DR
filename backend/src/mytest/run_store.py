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
    def complete_run(self, run_id: str) -> None: ...
    def get_run(self, run_id: str) -> dict[str, Any] | None: ...


class InMemoryResearchRunStore:
    """"内存实现：存储最近 N 次研究运行的完整时间线，线程安全。"""

    def __init__(self, max_runs: int = 100) -> None:
        self._max_runs = max_runs
        self._runs: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def start_run(self, *, run_id: str, topic: str) -> None:
        with self._lock:
            self._runs[run_id]={
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

    def complete_run(self, run_id:str)->None:
         with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                run["status"] = "completed"

    def get_run(self, run_id: str)-> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            snapshot = dict(run)
            snapshot["events"] = list(run["events"])
            return snapshot
    def _evict_if_needed(self) -> None:
        """SQLite 实现：持久化研究运行和事件，服务重启后仍可查询。"""

        def __init__(self, db_path: str | Path) -> None:
            self._db_path = Path(db_path)
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._lock = RLock()
            self._init_schema()
            

        def start_run(self, *, run_id: str, topic: str) -> None:
            with self._lock, self._connect() as conn:
                exists = conn.execute(
                    "DELETE FROM runs WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                if exists is None:
                    return 
                conn.execute(
                    """
                    INSERT INTO runs (run_id, topic, status) 
                    VALUES (?,?,'running')
                    ON CONFLICT(run_id) DO UPDATE SET
                        topic= excluded.topic,
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
                
    def complete_run(self, run_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE research_runs SET status = 'completed' WHERE run_id = ?",
                (run_id,),
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            run = conn.execute(
                "SELECT run_id, topic, status FROM research_runs WHERE run_id = ?",
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
        return {
            "run_id": run["run_id"],
            "topic": run["topic"],
            "status": run["status"],
            "events": [json.loads(row["payload_json"]) for row in events],
        }

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            run = conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_runs(
                    run_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_events(
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
                """
                CREATE INDEX IF NOT EXISTS idx_research_events_run_id ON research_events(run_id)
                """
            )
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn