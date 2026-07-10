from __future__ import annotations

from threading import Event

from services.active_run_registry import ActiveRunRegistry


def test_active_run_registry_requests_cancel_for_registered_run() -> None:
    registry = ActiveRunRegistry()
    stop_event = Event()
    registry.register("run-1", stop_event)

    assert registry.request_cancel("run-1") is True
    assert stop_event.is_set()


def test_active_run_registry_returns_false_for_unknown_run() -> None:
    registry = ActiveRunRegistry()

    assert registry.request_cancel("missing") is False


def test_active_run_registry_unregister_removes_active_run() -> None:
    registry = ActiveRunRegistry()
    stop_event = Event()
    registry.register("run-1", stop_event)
    registry.unregister("run-1")

    assert registry.is_active("run-1") is False
    assert registry.request_cancel("run-1") is False