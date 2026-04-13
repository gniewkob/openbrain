"""Tests for src/lifespan.py — startup, shutdown, and periodic sync paths."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _null_session():
    """Minimal no-op DB session for lifespan tests."""
    yield AsyncMock()


class _NullSessionMaker:
    def __call__(self):
        return _null_session()


def _make_config(public_mode=False, public_base_url="", redis_url="memory://"):
    cfg = MagicMock()
    cfg.auth.public_mode = public_mode
    cfg.auth.public_base_url = public_base_url
    cfg.redis.url = redis_url
    return cfg


def _lifespan_patches(
    counters=None,
    histograms=None,
    gauges=None,
    public_mode=False,
    redis_url="memory://",
):
    """Return a dict of patch targets → return values for a standard lifespan test."""
    return {
        "src.lifespan.AsyncSessionLocal": _NullSessionMaker(),
        "src.lifespan.get_telemetry_counters": AsyncMock(return_value=counters or []),
        "src.lifespan.get_telemetry_histograms": AsyncMock(return_value=histograms or []),
        "src.lifespan.bulk_load_metrics": MagicMock(),
        "src.lifespan.bulk_load_histograms": MagicMock(),
        "src.lifespan.refresh_memory_gauges": AsyncMock(return_value=gauges or {}),
        "src.lifespan.upsert_telemetry_metrics": AsyncMock(),
        "src.lifespan.get_metrics_snapshot": MagicMock(
            return_value={"counters": {}, "histograms": {}}
        ),
        "src.lifespan.get_config": MagicMock(
            return_value=_make_config(public_mode=public_mode, redis_url=redis_url)
        ),
        "src.lifespan.close_embedding_client": AsyncMock(),
    }


# ---------------------------------------------------------------------------
# Startup: telemetry load
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_startup_loads_persisted_telemetry():
    """On startup, persisted counters and histograms are loaded into memory."""
    patches = _lifespan_patches(counters={"c": 1}, histograms={"h": []})
    with (
        patch("src.lifespan.AsyncSessionLocal", patches["src.lifespan.AsyncSessionLocal"]),
        patch("src.lifespan.get_telemetry_counters", patches["src.lifespan.get_telemetry_counters"]),
        patch("src.lifespan.get_telemetry_histograms", patches["src.lifespan.get_telemetry_histograms"]),
        patch("src.lifespan.bulk_load_metrics", patches["src.lifespan.bulk_load_metrics"]) as mock_blm,
        patch("src.lifespan.bulk_load_histograms", patches["src.lifespan.bulk_load_histograms"]) as mock_blh,
        patch("src.lifespan.refresh_memory_gauges", patches["src.lifespan.refresh_memory_gauges"]),
        patch("src.lifespan.upsert_telemetry_metrics", patches["src.lifespan.upsert_telemetry_metrics"]),
        patch("src.lifespan.get_metrics_snapshot", patches["src.lifespan.get_metrics_snapshot"]),
        patch("src.lifespan.get_config", patches["src.lifespan.get_config"]),
        patch("src.lifespan.close_embedding_client", patches["src.lifespan.close_embedding_client"]),
    ):
        from src.lifespan import lifespan

        async with lifespan(None):
            pass

    mock_blm.assert_called_once_with({"c": 1})
    mock_blh.assert_called_once_with({"h": []})


@pytest.mark.asyncio
async def test_startup_skips_bulk_load_when_no_persisted_data():
    """bulk_load_* NOT called when persisted counters and histograms are empty."""
    patches = _lifespan_patches(counters=[], histograms=[])
    with (
        patch("src.lifespan.AsyncSessionLocal", patches["src.lifespan.AsyncSessionLocal"]),
        patch("src.lifespan.get_telemetry_counters", patches["src.lifespan.get_telemetry_counters"]),
        patch("src.lifespan.get_telemetry_histograms", patches["src.lifespan.get_telemetry_histograms"]),
        patch("src.lifespan.bulk_load_metrics", patches["src.lifespan.bulk_load_metrics"]) as mock_blm,
        patch("src.lifespan.bulk_load_histograms", patches["src.lifespan.bulk_load_histograms"]) as mock_blh,
        patch("src.lifespan.refresh_memory_gauges", patches["src.lifespan.refresh_memory_gauges"]),
        patch("src.lifespan.upsert_telemetry_metrics", patches["src.lifespan.upsert_telemetry_metrics"]),
        patch("src.lifespan.get_metrics_snapshot", patches["src.lifespan.get_metrics_snapshot"]),
        patch("src.lifespan.get_config", patches["src.lifespan.get_config"]),
        patch("src.lifespan.close_embedding_client", patches["src.lifespan.close_embedding_client"]),
    ):
        from src.lifespan import lifespan

        async with lifespan(None):
            pass

    mock_blm.assert_not_called()
    mock_blh.assert_not_called()


@pytest.mark.asyncio
async def test_startup_telemetry_exception_does_not_crash():
    """Telemetry load exception is caught — startup completes normally."""
    patches = _lifespan_patches()
    patches["src.lifespan.get_telemetry_counters"] = AsyncMock(
        side_effect=Exception("DB unavailable")
    )
    with (
        patch("src.lifespan.AsyncSessionLocal", patches["src.lifespan.AsyncSessionLocal"]),
        patch("src.lifespan.get_telemetry_counters", patches["src.lifespan.get_telemetry_counters"]),
        patch("src.lifespan.get_telemetry_histograms", patches["src.lifespan.get_telemetry_histograms"]),
        patch("src.lifespan.bulk_load_metrics", patches["src.lifespan.bulk_load_metrics"]),
        patch("src.lifespan.bulk_load_histograms", patches["src.lifespan.bulk_load_histograms"]),
        patch("src.lifespan.refresh_memory_gauges", patches["src.lifespan.refresh_memory_gauges"]),
        patch("src.lifespan.upsert_telemetry_metrics", patches["src.lifespan.upsert_telemetry_metrics"]),
        patch("src.lifespan.get_metrics_snapshot", patches["src.lifespan.get_metrics_snapshot"]),
        patch("src.lifespan.get_config", patches["src.lifespan.get_config"]),
        patch("src.lifespan.close_embedding_client", patches["src.lifespan.close_embedding_client"]),
    ):
        from src.lifespan import lifespan

        # Must not raise
        async with lifespan(None):
            pass


# ---------------------------------------------------------------------------
# Startup: gauge refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_startup_refreshes_gauges():
    """On startup, refresh_memory_gauges is called."""
    patches = _lifespan_patches()
    with (
        patch("src.lifespan.AsyncSessionLocal", patches["src.lifespan.AsyncSessionLocal"]),
        patch("src.lifespan.get_telemetry_counters", patches["src.lifespan.get_telemetry_counters"]),
        patch("src.lifespan.get_telemetry_histograms", patches["src.lifespan.get_telemetry_histograms"]),
        patch("src.lifespan.bulk_load_metrics", patches["src.lifespan.bulk_load_metrics"]),
        patch("src.lifespan.bulk_load_histograms", patches["src.lifespan.bulk_load_histograms"]),
        patch("src.lifespan.refresh_memory_gauges", patches["src.lifespan.refresh_memory_gauges"]) as mock_rg,
        patch("src.lifespan.upsert_telemetry_metrics", patches["src.lifespan.upsert_telemetry_metrics"]),
        patch("src.lifespan.get_metrics_snapshot", patches["src.lifespan.get_metrics_snapshot"]),
        patch("src.lifespan.get_config", patches["src.lifespan.get_config"]),
        patch("src.lifespan.close_embedding_client", patches["src.lifespan.close_embedding_client"]),
    ):
        from src.lifespan import lifespan

        async with lifespan(None):
            pass

    mock_rg.assert_called_once()


@pytest.mark.asyncio
async def test_startup_gauge_exception_does_not_crash():
    """Gauge refresh exception is caught — startup completes normally."""
    patches = _lifespan_patches()
    patches["src.lifespan.refresh_memory_gauges"] = AsyncMock(
        side_effect=Exception("gauge error")
    )
    with (
        patch("src.lifespan.AsyncSessionLocal", patches["src.lifespan.AsyncSessionLocal"]),
        patch("src.lifespan.get_telemetry_counters", patches["src.lifespan.get_telemetry_counters"]),
        patch("src.lifespan.get_telemetry_histograms", patches["src.lifespan.get_telemetry_histograms"]),
        patch("src.lifespan.bulk_load_metrics", patches["src.lifespan.bulk_load_metrics"]),
        patch("src.lifespan.bulk_load_histograms", patches["src.lifespan.bulk_load_histograms"]),
        patch("src.lifespan.refresh_memory_gauges", patches["src.lifespan.refresh_memory_gauges"]),
        patch("src.lifespan.upsert_telemetry_metrics", patches["src.lifespan.upsert_telemetry_metrics"]),
        patch("src.lifespan.get_metrics_snapshot", patches["src.lifespan.get_metrics_snapshot"]),
        patch("src.lifespan.get_config", patches["src.lifespan.get_config"]),
        patch("src.lifespan.close_embedding_client", patches["src.lifespan.close_embedding_client"]),
    ):
        from src.lifespan import lifespan

        async with lifespan(None):
            pass


# ---------------------------------------------------------------------------
# Startup: Redis guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_startup_raises_when_public_mode_and_memory_redis():
    """PUBLIC_MODE=true + REDIS_URL=memory:// must raise RuntimeError at startup."""
    patches = _lifespan_patches(public_mode=True, redis_url="memory://")
    with (
        patch("src.lifespan.AsyncSessionLocal", patches["src.lifespan.AsyncSessionLocal"]),
        patch("src.lifespan.get_telemetry_counters", patches["src.lifespan.get_telemetry_counters"]),
        patch("src.lifespan.get_telemetry_histograms", patches["src.lifespan.get_telemetry_histograms"]),
        patch("src.lifespan.bulk_load_metrics", patches["src.lifespan.bulk_load_metrics"]),
        patch("src.lifespan.bulk_load_histograms", patches["src.lifespan.bulk_load_histograms"]),
        patch("src.lifespan.refresh_memory_gauges", patches["src.lifespan.refresh_memory_gauges"]),
        patch("src.lifespan.upsert_telemetry_metrics", patches["src.lifespan.upsert_telemetry_metrics"]),
        patch("src.lifespan.get_metrics_snapshot", patches["src.lifespan.get_metrics_snapshot"]),
        patch("src.lifespan.get_config", patches["src.lifespan.get_config"]),
        patch("src.lifespan.close_embedding_client", patches["src.lifespan.close_embedding_client"]),
    ):
        from src.lifespan import lifespan

        with pytest.raises(RuntimeError, match="REDIS_URL"):
            async with lifespan(None):
                pass


@pytest.mark.asyncio
async def test_startup_ok_when_public_mode_and_real_redis():
    """PUBLIC_MODE=true with a real Redis URL passes the guard."""
    patches = _lifespan_patches(public_mode=True, redis_url="redis://localhost:6379/0")
    with (
        patch("src.lifespan.AsyncSessionLocal", patches["src.lifespan.AsyncSessionLocal"]),
        patch("src.lifespan.get_telemetry_counters", patches["src.lifespan.get_telemetry_counters"]),
        patch("src.lifespan.get_telemetry_histograms", patches["src.lifespan.get_telemetry_histograms"]),
        patch("src.lifespan.bulk_load_metrics", patches["src.lifespan.bulk_load_metrics"]),
        patch("src.lifespan.bulk_load_histograms", patches["src.lifespan.bulk_load_histograms"]),
        patch("src.lifespan.refresh_memory_gauges", patches["src.lifespan.refresh_memory_gauges"]),
        patch("src.lifespan.upsert_telemetry_metrics", patches["src.lifespan.upsert_telemetry_metrics"]),
        patch("src.lifespan.get_metrics_snapshot", patches["src.lifespan.get_metrics_snapshot"]),
        patch("src.lifespan.get_config", patches["src.lifespan.get_config"]),
        patch("src.lifespan.close_embedding_client", patches["src.lifespan.close_embedding_client"]),
    ):
        from src.lifespan import lifespan

        async with lifespan(None):
            pass  # no exception


# ---------------------------------------------------------------------------
# Shutdown paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_cancels_sync_task():
    """The periodic sync task is cancelled on shutdown."""
    patches = _lifespan_patches()
    task_ref = {}

    original_create_task = asyncio.create_task

    def _capture_task(coro, **kw):
        t = original_create_task(coro, **kw)
        task_ref["task"] = t
        return t

    with (
        patch("src.lifespan.AsyncSessionLocal", patches["src.lifespan.AsyncSessionLocal"]),
        patch("src.lifespan.get_telemetry_counters", patches["src.lifespan.get_telemetry_counters"]),
        patch("src.lifespan.get_telemetry_histograms", patches["src.lifespan.get_telemetry_histograms"]),
        patch("src.lifespan.bulk_load_metrics", patches["src.lifespan.bulk_load_metrics"]),
        patch("src.lifespan.bulk_load_histograms", patches["src.lifespan.bulk_load_histograms"]),
        patch("src.lifespan.refresh_memory_gauges", patches["src.lifespan.refresh_memory_gauges"]),
        patch("src.lifespan.upsert_telemetry_metrics", patches["src.lifespan.upsert_telemetry_metrics"]),
        patch("src.lifespan.get_metrics_snapshot", patches["src.lifespan.get_metrics_snapshot"]),
        patch("src.lifespan.get_config", patches["src.lifespan.get_config"]),
        patch("src.lifespan.close_embedding_client", patches["src.lifespan.close_embedding_client"]),
        patch("asyncio.create_task", side_effect=_capture_task),
    ):
        from src.lifespan import lifespan

        async with lifespan(None):
            pass

    assert "task" in task_ref
    assert task_ref["task"].cancelled() or task_ref["task"].done()


@pytest.mark.asyncio
async def test_shutdown_calls_final_flush():
    """upsert_telemetry_metrics is called on shutdown for final flush."""
    patches = _lifespan_patches()
    with (
        patch("src.lifespan.AsyncSessionLocal", patches["src.lifespan.AsyncSessionLocal"]),
        patch("src.lifespan.get_telemetry_counters", patches["src.lifespan.get_telemetry_counters"]),
        patch("src.lifespan.get_telemetry_histograms", patches["src.lifespan.get_telemetry_histograms"]),
        patch("src.lifespan.bulk_load_metrics", patches["src.lifespan.bulk_load_metrics"]),
        patch("src.lifespan.bulk_load_histograms", patches["src.lifespan.bulk_load_histograms"]),
        patch("src.lifespan.refresh_memory_gauges", patches["src.lifespan.refresh_memory_gauges"]),
        patch("src.lifespan.upsert_telemetry_metrics", patches["src.lifespan.upsert_telemetry_metrics"]) as mock_upsert,
        patch("src.lifespan.get_metrics_snapshot", patches["src.lifespan.get_metrics_snapshot"]),
        patch("src.lifespan.get_config", patches["src.lifespan.get_config"]),
        patch("src.lifespan.close_embedding_client", patches["src.lifespan.close_embedding_client"]),
    ):
        from src.lifespan import lifespan

        async with lifespan(None):
            pass

    # Called at least once on shutdown (may also be called by periodic sync if it ran)
    assert mock_upsert.called


@pytest.mark.asyncio
async def test_shutdown_final_flush_exception_does_not_reraise():
    """Final flush exception is caught — shutdown completes normally."""
    patches = _lifespan_patches()
    patches["src.lifespan.upsert_telemetry_metrics"] = AsyncMock(
        side_effect=Exception("flush failed")
    )
    with (
        patch("src.lifespan.AsyncSessionLocal", patches["src.lifespan.AsyncSessionLocal"]),
        patch("src.lifespan.get_telemetry_counters", patches["src.lifespan.get_telemetry_counters"]),
        patch("src.lifespan.get_telemetry_histograms", patches["src.lifespan.get_telemetry_histograms"]),
        patch("src.lifespan.bulk_load_metrics", patches["src.lifespan.bulk_load_metrics"]),
        patch("src.lifespan.bulk_load_histograms", patches["src.lifespan.bulk_load_histograms"]),
        patch("src.lifespan.refresh_memory_gauges", patches["src.lifespan.refresh_memory_gauges"]),
        patch("src.lifespan.upsert_telemetry_metrics", patches["src.lifespan.upsert_telemetry_metrics"]),
        patch("src.lifespan.get_metrics_snapshot", patches["src.lifespan.get_metrics_snapshot"]),
        patch("src.lifespan.get_config", patches["src.lifespan.get_config"]),
        patch("src.lifespan.close_embedding_client", patches["src.lifespan.close_embedding_client"]),
    ):
        from src.lifespan import lifespan

        async with lifespan(None):
            pass  # must not raise


@pytest.mark.asyncio
async def test_shutdown_closes_embedding_client():
    """close_embedding_client is called on shutdown."""
    patches = _lifespan_patches()
    with (
        patch("src.lifespan.AsyncSessionLocal", patches["src.lifespan.AsyncSessionLocal"]),
        patch("src.lifespan.get_telemetry_counters", patches["src.lifespan.get_telemetry_counters"]),
        patch("src.lifespan.get_telemetry_histograms", patches["src.lifespan.get_telemetry_histograms"]),
        patch("src.lifespan.bulk_load_metrics", patches["src.lifespan.bulk_load_metrics"]),
        patch("src.lifespan.bulk_load_histograms", patches["src.lifespan.bulk_load_histograms"]),
        patch("src.lifespan.refresh_memory_gauges", patches["src.lifespan.refresh_memory_gauges"]),
        patch("src.lifespan.upsert_telemetry_metrics", patches["src.lifespan.upsert_telemetry_metrics"]),
        patch("src.lifespan.get_metrics_snapshot", patches["src.lifespan.get_metrics_snapshot"]),
        patch("src.lifespan.get_config", patches["src.lifespan.get_config"]),
        patch("src.lifespan.close_embedding_client", patches["src.lifespan.close_embedding_client"]) as mock_close,
    ):
        from src.lifespan import lifespan

        async with lifespan(None):
            pass

    mock_close.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_embedding_exception_does_not_reraise():
    """close_embedding_client exception is caught — shutdown completes normally."""
    patches = _lifespan_patches()
    patches["src.lifespan.close_embedding_client"] = AsyncMock(
        side_effect=Exception("close failed")
    )
    with (
        patch("src.lifespan.AsyncSessionLocal", patches["src.lifespan.AsyncSessionLocal"]),
        patch("src.lifespan.get_telemetry_counters", patches["src.lifespan.get_telemetry_counters"]),
        patch("src.lifespan.get_telemetry_histograms", patches["src.lifespan.get_telemetry_histograms"]),
        patch("src.lifespan.bulk_load_metrics", patches["src.lifespan.bulk_load_metrics"]),
        patch("src.lifespan.bulk_load_histograms", patches["src.lifespan.bulk_load_histograms"]),
        patch("src.lifespan.refresh_memory_gauges", patches["src.lifespan.refresh_memory_gauges"]),
        patch("src.lifespan.upsert_telemetry_metrics", patches["src.lifespan.upsert_telemetry_metrics"]),
        patch("src.lifespan.get_metrics_snapshot", patches["src.lifespan.get_metrics_snapshot"]),
        patch("src.lifespan.get_config", patches["src.lifespan.get_config"]),
        patch("src.lifespan.close_embedding_client", patches["src.lifespan.close_embedding_client"]),
    ):
        from src.lifespan import lifespan

        async with lifespan(None):
            pass  # must not raise


# ---------------------------------------------------------------------------
# periodic_telemetry_sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_periodic_sync_runs_one_iteration():
    """periodic_telemetry_sync syncs telemetry once when sleep is fast."""
    synced = []

    async def _fast_sleep(n):
        if len(synced) >= 1:
            raise asyncio.CancelledError
        synced.append(n)

    mock_snapshot = MagicMock(return_value={"counters": {"c": 1}, "histograms": {}})
    mock_upsert = AsyncMock()
    mock_gauges = AsyncMock(return_value={})

    with (
        patch("src.lifespan.asyncio.sleep", side_effect=_fast_sleep),
        patch("src.lifespan.get_metrics_snapshot", mock_snapshot),
        patch("src.lifespan.upsert_telemetry_metrics", mock_upsert),
        patch("src.lifespan.refresh_memory_gauges", mock_gauges),
        patch("src.lifespan.AsyncSessionLocal", _NullSessionMaker()),
    ):
        from src.lifespan import periodic_telemetry_sync

        with pytest.raises(asyncio.CancelledError):
            await periodic_telemetry_sync()

    mock_upsert.assert_called_once()


@pytest.mark.asyncio
async def test_periodic_sync_exception_continues_loop():
    """Exceptions in periodic_telemetry_sync are caught and the loop continues."""
    iteration = {"count": 0}

    async def _fast_sleep(n):
        if iteration["count"] >= 2:
            raise asyncio.CancelledError

    async def _failing_upsert(*a, **kw):
        iteration["count"] += 1
        raise Exception("transient error")

    with (
        patch("src.lifespan.asyncio.sleep", side_effect=_fast_sleep),
        patch("src.lifespan.get_metrics_snapshot", MagicMock(return_value={"counters": {}, "histograms": {}})),
        patch("src.lifespan.upsert_telemetry_metrics", side_effect=_failing_upsert),
        patch("src.lifespan.refresh_memory_gauges", AsyncMock(return_value={})),
        patch("src.lifespan.AsyncSessionLocal", _NullSessionMaker()),
    ):
        from src.lifespan import periodic_telemetry_sync

        with pytest.raises(asyncio.CancelledError):
            await periodic_telemetry_sync()

    # Loop ran at least twice despite exceptions
    assert iteration["count"] >= 2
