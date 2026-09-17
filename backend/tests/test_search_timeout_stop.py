import sys
from threading import Event, Lock
from types import SimpleNamespace

import pytest

from config import Configuration, SearchAPI
from services.cancellation import ResearchCancelled
from services.search_backends import FallbackSearchBackend
from services.task_executor import TaskExecutor


@pytest.mark.parametrize("injected", [True, False])
@pytest.mark.parametrize("with_parent", [True, False])
def test_search_timeout_stops_late_retries_without_cancelling_run(
    monkeypatch, injected, with_parent,
):
    started, release, finished = Event(), Event(), Event()
    parent = Event() if with_parent else None
    attempts, worker_errors = [], []
    config = Configuration(
        search_api=SearchAPI.DUCKDUCKGO, search_fallback_chain=[],
        search_timeout_seconds=1, enable_notes=False,
    )

    class FakeDDGS:
        def __init__(self, *, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def text(self, query, *, max_results, backend):
            attempts.append((query, backend))
            if query == "first" and backend == "lite":
                started.set()
                if not release.wait(3):
                    raise AssertionError("test did not release search")
                raise RuntimeError("late failure")
            return [{"title": "A", "href": "https://example.com"}]

    original = FallbackSearchBackend.search_with_cancellation

    def tracked(self, query, **kwargs):
        try:
            return original(self, query, **kwargs)
        except ResearchCancelled as exc:
            worker_errors.append(exc)
            raise
        finally:
            finished.set()

    clock_calls = [0]

    def clock():
        clock_calls[0] += 1
        if clock_calls[0] == 1:
            return 0.0
        assert started.wait(2), "worker did not start"
        return 2.0

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
    # Keep the adapter budget available: the caller's timeout must stop retries.
    monkeypatch.setattr("services.search_backends.monotonic", lambda: 0.0)
    monkeypatch.setattr(FallbackSearchBackend, "search_with_cancellation", tracked)
    executor = TaskExecutor(
        config=config, summarizer=None, state_lock=Lock(),
        drain_tool_events=lambda *args, **kwargs: [], monotonic_clock=clock,
        search_backend=FallbackSearchBackend(config) if injected else None,
    )
    try:
        with pytest.raises(TimeoutError, match="搜索超时"):
            executor._run_search_with_timeout("first", 0, stop_event=parent)
        assert not finished.is_set(), "caller should return before the SDK finishes"
    finally:
        release.set()
        assert finished.wait(3), "search worker did not exit"

    assert attempts == [("first", "lite")]
    assert len(worker_errors) == 1
    assert parent is None or not parent.is_set()

    # The same executor and run can perform a subsequent independent search.
    executor._monotonic_clock = lambda: 0.0
    result, _, _, backend = executor._run_search_with_timeout("second", 0, stop_event=parent)
    assert result["results"] and backend == "duckduckgo"
    assert attempts == [("first", "lite"), ("second", "lite")]
    assert parent is None or not parent.is_set()
