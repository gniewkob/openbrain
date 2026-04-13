"""Tests for Redis-backed sliding-window rate limiter in src/auth.py."""

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_mock(zcard_return=0):
    """Return a mock Redis client whose pipeline returns deterministic results."""
    pipe = MagicMock()
    # pipeline().zremrangebyscore().zadd().zcard().expire().execute()
    # results = [None, 1, zcard_return, True]
    pipe.execute.return_value = [None, 1, zcard_return, True]
    client = MagicMock()
    client.pipeline.return_value = pipe
    return client, pipe


# ---------------------------------------------------------------------------
# _get_redis_client
# ---------------------------------------------------------------------------


def test_get_redis_client_returns_none_for_memory_url():
    """When REDIS_URL=memory:// (default), no Redis client is created."""
    import src.auth as auth_mod

    # Reset singleton
    auth_mod._redis_client = None
    with patch.dict("os.environ", {"REDIS_URL": "memory://"}):
        result = auth_mod._get_redis_client()
    assert result is None


def test_get_redis_client_returns_none_when_redis_unavailable():
    """When Redis connection fails, _get_redis_client returns None (fallback)."""
    import src.auth as auth_mod

    auth_mod._redis_client = None
    with (
        patch.dict("os.environ", {"REDIS_URL": "redis://localhost:9999"}),
        patch("redis.Redis.from_url", side_effect=Exception("connection refused")),
    ):
        result = auth_mod._get_redis_client()
    assert result is None
    auth_mod._redis_client = None  # cleanup


def test_get_redis_client_caches_singleton():
    """_get_redis_client returns the same instance on repeated calls."""
    import src.auth as auth_mod

    mock_client = MagicMock()
    mock_client.ping.return_value = True
    auth_mod._redis_client = mock_client

    result1 = auth_mod._get_redis_client()
    result2 = auth_mod._get_redis_client()
    assert result1 is result2 is mock_client

    auth_mod._redis_client = None  # cleanup


# ---------------------------------------------------------------------------
# _rate_limit_redis
# ---------------------------------------------------------------------------


def test_rate_limit_redis_allows_under_limit():
    """Requests below the rate limit pass without raising."""
    from src.auth import _rate_limit_redis

    client, _ = _make_redis_mock(zcard_return=5)
    _rate_limit_redis(client, "1.2.3.4", limit=10)  # count=5 < limit=10 → OK


def test_rate_limit_redis_raises_429_at_limit():
    """Requests at or above the rate limit raise HTTP 429."""
    from src.auth import _rate_limit_redis

    client, _ = _make_redis_mock(zcard_return=11)
    with pytest.raises(HTTPException) as exc_info:
        _rate_limit_redis(client, "1.2.3.4", limit=10)
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_rate_limit_redis_pipeline_includes_expire():
    """Pipeline includes EXPIRE so stale keys are cleaned up."""
    from src.auth import _rate_limit_redis

    client, pipe = _make_redis_mock(zcard_return=1)
    _rate_limit_redis(client, "1.2.3.4", limit=100)
    pipe.expire.assert_called_once()
    args = pipe.expire.call_args[0]
    assert "1.2.3.4" in args[0]  # key contains IP
    assert args[1] == 61  # TTL


def test_rate_limit_redis_pipeline_removes_old_entries():
    """Pipeline calls ZREMRANGEBYSCORE to slide the window."""
    from src.auth import _rate_limit_redis

    client, pipe = _make_redis_mock(zcard_return=1)
    before = time.time()
    _rate_limit_redis(client, "1.2.3.4", limit=100)
    pipe.zremrangebyscore.assert_called_once()
    _key, low, high = pipe.zremrangebyscore.call_args[0]
    assert low == 0
    assert before - 60.0 <= high <= time.time()


# ---------------------------------------------------------------------------
# _rate_limit_memory
# ---------------------------------------------------------------------------


def test_rate_limit_memory_allows_under_limit():
    """In-memory limiter allows requests under the limit."""
    import src.auth as auth_mod

    auth_mod._rate_limit_store.clear()
    from src.auth import _rate_limit_memory

    for _ in range(5):
        _rate_limit_memory("10.0.0.1", limit=10)

    auth_mod._rate_limit_store.clear()


def test_rate_limit_memory_raises_429_at_limit():
    """In-memory limiter raises 429 when limit is reached."""
    import src.auth as auth_mod

    auth_mod._rate_limit_store.clear()
    from src.auth import _rate_limit_memory

    for _ in range(10):
        _rate_limit_memory("10.0.0.2", limit=10)
    with pytest.raises(HTTPException) as exc_info:
        _rate_limit_memory("10.0.0.2", limit=10)
    assert exc_info.value.status_code == 429

    auth_mod._rate_limit_store.clear()


def test_rate_limit_memory_slides_window():
    """Old requests outside the 60s window are discarded."""
    import src.auth as auth_mod

    auth_mod._rate_limit_store.clear()
    from src.auth import _rate_limit_memory

    # Seed 9 stale timestamps (>60s ago)
    stale_time = time.time() - 120.0
    auth_mod._rate_limit_store["10.0.0.3"] = __import__("collections").deque(
        [stale_time] * 9
    )
    # With limit=10 and 9 stale entries (discarded), this request should pass
    _rate_limit_memory("10.0.0.3", limit=10)

    auth_mod._rate_limit_store.clear()


# ---------------------------------------------------------------------------
# check_internal_key_rate_limit — integration
# ---------------------------------------------------------------------------


def test_check_rate_limit_uses_redis_when_available():
    """check_internal_key_rate_limit delegates to Redis when client is available."""
    import src.auth as auth_mod

    mock_client, _ = _make_redis_mock(zcard_return=1)
    auth_mod._redis_client = mock_client

    with patch("src.auth._rate_limit_redis") as mock_redis_rl:
        auth_mod.check_internal_key_rate_limit("1.1.1.1")
        mock_redis_rl.assert_called_once_with(mock_client, "1.1.1.1", auth_mod._get_rate_limit_rpm())

    auth_mod._redis_client = None


def test_check_rate_limit_falls_back_to_memory_when_redis_fails():
    """If Redis raises an unexpected error, in-memory fallback is used."""
    import src.auth as auth_mod

    mock_client = MagicMock()
    auth_mod._redis_client = mock_client
    auth_mod._rate_limit_store.clear()

    with patch("src.auth._rate_limit_redis", side_effect=Exception("redis error")):
        with patch("src.auth._rate_limit_memory") as mock_mem_rl:
            auth_mod.check_internal_key_rate_limit("2.2.2.2")
            mock_mem_rl.assert_called_once()

    auth_mod._redis_client = None
    auth_mod._rate_limit_store.clear()


def test_check_rate_limit_uses_memory_when_no_redis():
    """When no Redis client, in-memory limiter is used directly."""
    import src.auth as auth_mod

    auth_mod._redis_client = None
    auth_mod._rate_limit_store.clear()

    with (
        patch.dict("os.environ", {"REDIS_URL": "memory://"}),
        patch("src.auth._rate_limit_memory") as mock_mem_rl,
    ):
        auth_mod.check_internal_key_rate_limit("3.3.3.3")
        mock_mem_rl.assert_called_once()

    auth_mod._rate_limit_store.clear()
