from __future__ import annotations

from threading import Event

from main import CancelResearchRunResponse, create_app
from services.run_cancellation_registry import MemoryRunCancellationRegistry
from services.research_run_store import InMemoryResearchRunStore


def _find_route(app, path: str, method: str):
    for route in app.routes:
        if getattr(route, "path", "") == path and method in getattr(route, "methods", set()):
            return route
    raise AssertionError(f"route not found: {method} {path}")


def test_cancel_research_run_triggers_registered_stop_event() -> None:
    app = create_app()
    registry: MemoryRunCancellationRegistry = app.state.run_cancellation_registry
    run_store: InMemoryResearchRunStore = app.state.run_store

    stop_event = Event()
    run_store.start_run(run_id="run-cancel-001", topic="取消测试")
    registry.register("run-cancel-001", stop_event)

    route = _find_route(app, "/research/runs/{run_id}/cancel", "POST")
    response = route.endpoint("run-cancel-001")

    assert response == CancelResearchRunResponse(
        run_id="run-cancel-001",
        cancelled=True,
        status="cancelling",
        message="已发送取消信号，后台任务将尽快停止",
    )
    assert stop_event.is_set()


def test_cancel_research_run_returns_false_for_completed_run() -> None:
    app = create_app()
    run_store: InMemoryResearchRunStore = app.state.run_store
    run_store.start_run(run_id="run-done", topic="已完成")
    run_store.complete_run("run-done")

    route = _find_route(app, "/research/runs/{run_id}/cancel", "POST")
    response = route.endpoint("run-done")

    assert response.cancelled is False
    assert response.status == "completed"