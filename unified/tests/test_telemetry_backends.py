"""Tests for InMemoryCounterBackend and RedisCounterBackend implementations."""

import sys
from unittest.mock import MagicMock, patch

import pytest


KNOWN = ("requests_total", "errors_total", "cache_hits_total")


# ---------------------------------------------------------------------------
# InMemoryCounterBackend
# ---------------------------------------------------------------------------


def test_initial_known_counters_are_zero():
    from src.telemetry_counters import InMemoryCounterBackend

    backend = InMemoryCounterBackend(KNOWN)
    snap = backend.snapshot()
    for name in KNOWN:
        assert snap[name] == 0


def test_incr_known_counter_by_one():
    from src.telemetry_counters import InMemoryCounterBackend

    backend = InMemoryCounterBackend(KNOWN)
    backend.incr("requests_total")
    assert backend.snapshot()["requests_total"] == 1


def test_incr_by_custom_value():
    from src.telemetry_counters import InMemoryCounterBackend

    backend = InMemoryCounterBackend(KNOWN)
    backend.incr("requests_total", 5)
    assert backend.snapshot()["requests_total"] == 5


def test_incr_unknown_counter_is_tracked():
    from src.telemetry_counters import InMemoryCounterBackend

    backend = InMemoryCounterBackend(KNOWN)
    backend.incr("dynamic_counter")
    assert backend.snapshot()["dynamic_counter"] == 1


def test_snapshot_is_sorted_by_name():
    from src.telemetry_counters import InMemoryCounterBackend

    backend = InMemoryCounterBackend(("z_counter", "a_counter"))
    keys = list(backend.snapshot().keys())
    assert keys == sorted(keys)


def test_bulk_load_restores_known_counters():
    from src.telemetry_counters import InMemoryCounterBackend

    backend = InMemoryCounterBackend(KNOWN)
    backend.bulk_load({"requests_total": 42, "errors_total": 7})
    snap = backend.snapshot()
    assert snap["requests_total"] == 42
    assert snap["errors_total"] == 7


def test_bulk_load_ignores_fully_unknown_keys():
    from src.telemetry_counters import InMemoryCounterBackend

    backend = InMemoryCounterBackend(KNOWN)
    backend.bulk_load({"totally_unknown": 99})
    snap = backend.snapshot()
    assert snap.get("totally_unknown", 0) == 0


def test_bulk_load_allows_http_requests_prefix():
    from src.telemetry_counters import InMemoryCounterBackend

    backend = InMemoryCounterBackend(KNOWN)
    backend.bulk_load({"http_requests_total_GET_200": 15})
    assert backend.snapshot()["http_requests_total_GET_200"] == 15


def test_reset_clears_and_reseeds():
    from src.telemetry_counters import InMemoryCounterBackend

    backend = InMemoryCounterBackend(KNOWN)
    backend.incr("requests_total", 100)
    backend.reset()
    snap = backend.snapshot()
    assert snap["requests_total"] == 0
    for name in KNOWN:
        assert name in snap


def test_reset_removes_unknown_counters():
    from src.telemetry_counters import InMemoryCounterBackend

    backend = InMemoryCounterBackend(KNOWN)
    backend.incr("ephemeral_counter", 5)
    backend.reset()
    assert "ephemeral_counter" not in backend.snapshot()


def test_multiple_incr_accumulate():
    from src.telemetry_counters import InMemoryCounterBackend

    backend = InMemoryCounterBackend(KNOWN)
    backend.incr("requests_total", 3)
    backend.incr("requests_total", 7)
    assert backend.snapshot()["requests_total"] == 10


# ---------------------------------------------------------------------------
# RedisCounterBackend — import error
# ---------------------------------------------------------------------------


def test_redis_backend_raises_on_missing_redis_import():
    from src.telemetry_counters import RedisCounterBackend

    original = sys.modules.get("redis")
    try:
        sys.modules["redis"] = None  # type: ignore[assignment]
        with pytest.raises(RuntimeError, match="redis package"):
            RedisCounterBackend(
                redis_url="redis://localhost:6379", known_counters=KNOWN
            )
    finally:
        if original is not None:
            sys.modules["redis"] = original
        else:
            sys.modules.pop("redis", None)


# ---------------------------------------------------------------------------
# RedisCounterBackend — mocked client
# ---------------------------------------------------------------------------


def _make_redis_client(hgetall_return=None):
    client = MagicMock()
    pipe = MagicMock()
    pipe.execute.return_value = []
    client.pipeline.return_value = pipe
    client.hgetall.return_value = hgetall_return or {}
    return client


def test_redis_backend_incr_calls_hincrby():
    from src.telemetry_counters import RedisCounterBackend

    client = _make_redis_client()
    with patch("redis.Redis.from_url", return_value=client):
        backend = RedisCounterBackend(
            redis_url="redis://localhost:6379", known_counters=KNOWN
        )
        backend.incr("requests_total", 3)

    client.hincrby.assert_called_once_with(
        "openbrain:telemetry:counters", "requests_total", 3
    )


def test_redis_backend_snapshot_parses_values():
    from src.telemetry_counters import RedisCounterBackend

    client = _make_redis_client(
        hgetall_return={"requests_total": "5", "errors_total": "2"}
    )
    with patch("redis.Redis.from_url", return_value=client):
        backend = RedisCounterBackend(
            redis_url="redis://localhost:6379", known_counters=KNOWN
        )
        snap = backend.snapshot()

    assert snap["requests_total"] == 5
    assert snap["errors_total"] == 2


def test_redis_backend_snapshot_fills_missing_known_counters():
    from src.telemetry_counters import RedisCounterBackend

    client = _make_redis_client(hgetall_return={})
    with patch("redis.Redis.from_url", return_value=client):
        backend = RedisCounterBackend(
            redis_url="redis://localhost:6379", known_counters=KNOWN
        )
        snap = backend.snapshot()

    for name in KNOWN:
        assert name in snap
        assert snap[name] == 0


def test_redis_backend_snapshot_skips_non_int_values():
    from src.telemetry_counters import RedisCounterBackend

    client = _make_redis_client(hgetall_return={"bad": "not_an_int"})
    with patch("redis.Redis.from_url", return_value=client):
        backend = RedisCounterBackend(
            redis_url="redis://localhost:6379", known_counters=KNOWN
        )
        snap = backend.snapshot()

    assert "bad" not in snap


def test_redis_backend_bulk_load_writes_known():
    from src.telemetry_counters import RedisCounterBackend

    client = _make_redis_client()
    pipe = client.pipeline.return_value
    with patch("redis.Redis.from_url", return_value=client):
        backend = RedisCounterBackend(
            redis_url="redis://localhost:6379", known_counters=KNOWN
        )
        backend.bulk_load({"requests_total": 10})

    pipe.hset.assert_called()


def test_redis_backend_bulk_load_empty_is_noop():
    from src.telemetry_counters import RedisCounterBackend

    client = _make_redis_client()
    with patch("redis.Redis.from_url", return_value=client):
        backend = RedisCounterBackend(
            redis_url="redis://localhost:6379", known_counters=KNOWN
        )
        call_count_before = client.pipeline.call_count
        backend.bulk_load({})

    # No additional pipeline call beyond _seed
    assert client.pipeline.call_count == call_count_before


def test_redis_backend_reset_deletes_hash():
    from src.telemetry_counters import RedisCounterBackend

    client = _make_redis_client()
    with patch("redis.Redis.from_url", return_value=client):
        backend = RedisCounterBackend(
            redis_url="redis://localhost:6379", known_counters=KNOWN
        )
        backend.reset()

    client.delete.assert_called_once_with("openbrain:telemetry:counters")
