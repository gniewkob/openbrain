from __future__ import annotations

from unittest.mock import patch

from src.telemetry_counters import (
    CounterBackendBuildMeta,
    InMemoryCounterBackend,
    build_counter_backend,
    build_counter_backend_with_meta,
)


def test_build_counter_backend_defaults_to_memory(monkeypatch) -> None:
    monkeypatch.delenv("TELEMETRY_BACKEND", raising=False)
    backend = build_counter_backend(("memories_created_total",))
    assert isinstance(backend, InMemoryCounterBackend)


def test_build_counter_backend_redis_without_url_falls_back_to_memory(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TELEMETRY_BACKEND", "redis")
    monkeypatch.delenv("TELEMETRY_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    backend = build_counter_backend(("memories_created_total",))
    assert isinstance(backend, InMemoryCounterBackend)


def test_build_counter_backend_redis_failure_falls_back_to_memory(monkeypatch) -> None:
    monkeypatch.setenv("TELEMETRY_BACKEND", "redis")
    monkeypatch.setenv("TELEMETRY_REDIS_URL", "redis://localhost:6379/0")
    with patch(
        "src.telemetry_counters.RedisCounterBackend", side_effect=RuntimeError("boom")
    ):
        backend = build_counter_backend(("memories_created_total",))
    assert isinstance(backend, InMemoryCounterBackend)


def test_build_counter_backend_with_meta_reports_no_fallback_for_default_memory(
    monkeypatch,
) -> None:
    monkeypatch.delenv("TELEMETRY_BACKEND", raising=False)
    backend, meta = build_counter_backend_with_meta(("memories_created_total",))
    assert isinstance(backend, InMemoryCounterBackend)
    assert meta == CounterBackendBuildMeta(
        requested_backend="memory",
        selected_backend="memory",
        fallback_reason=None,
    )


def test_build_counter_backend_with_meta_reports_missing_redis_url(monkeypatch) -> None:
    monkeypatch.setenv("TELEMETRY_BACKEND", "redis")
    monkeypatch.delenv("TELEMETRY_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    backend, meta = build_counter_backend_with_meta(("memories_created_total",))
    assert isinstance(backend, InMemoryCounterBackend)
    assert meta.requested_backend == "redis"
    assert meta.selected_backend == "memory"
    assert meta.fallback_reason == "redis_url_missing"


def test_build_counter_backend_with_meta_reports_redis_constructor_failure(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TELEMETRY_BACKEND", "redis")
    monkeypatch.setenv("TELEMETRY_REDIS_URL", "redis://localhost:6379/0")
    with patch(
        "src.telemetry_counters.RedisCounterBackend", side_effect=RuntimeError("boom")
    ):
        backend, meta = build_counter_backend_with_meta(("memories_created_total",))
    assert isinstance(backend, InMemoryCounterBackend)
    assert meta.requested_backend == "redis"
    assert meta.selected_backend == "memory"
    assert meta.fallback_reason == "redis_unavailable:RuntimeError"
