from __future__ import annotations

from unittest.mock import patch

from src.telemetry_counters import (
    InMemoryCounterBackend,
    build_counter_backend,
)


def test_build_counter_backend_defaults_to_memory(monkeypatch) -> None:
    monkeypatch.delenv("TELEMETRY_BACKEND", raising=False)
    backend = build_counter_backend(("memories_created_total",))
    assert isinstance(backend, InMemoryCounterBackend)


def test_build_counter_backend_redis_without_url_falls_back_to_memory(monkeypatch) -> None:
    monkeypatch.setenv("TELEMETRY_BACKEND", "redis")
    monkeypatch.delenv("TELEMETRY_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    backend = build_counter_backend(("memories_created_total",))
    assert isinstance(backend, InMemoryCounterBackend)


def test_build_counter_backend_redis_failure_falls_back_to_memory(monkeypatch) -> None:
    monkeypatch.setenv("TELEMETRY_BACKEND", "redis")
    monkeypatch.setenv("TELEMETRY_REDIS_URL", "redis://localhost:6379/0")
    with patch("src.telemetry_counters.RedisCounterBackend", side_effect=RuntimeError("boom")):
        backend = build_counter_backend(("memories_created_total",))
    assert isinstance(backend, InMemoryCounterBackend)
