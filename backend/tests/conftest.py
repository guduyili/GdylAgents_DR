import pytest


@pytest.fixture
def isolated_run_configuration(monkeypatch, tmp_path):
    """Keep explicitly opted-in API tests off developer stores and Redis."""
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    monkeypatch.setenv("RUN_STORE_DB_PATH", str(tmp_path / "runs.sqlite3"))
    monkeypatch.setenv("CANCEL_BROADCAST_BACKEND", "memory")
