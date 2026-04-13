"""Tests for src/telemetry_store.py — DB-backed telemetry persistence."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _counter(name: str, value: int):
    c = MagicMock()
    c.name = name
    c.value = value
    return c


def _histogram(name: str, *, sum_: float, count: int, buckets, counts):
    h = MagicMock()
    h.name = name
    h.sum = sum_
    h.count = count
    h.buckets = buckets
    h.counts = counts
    return h


def _exec_result(scalars_all):
    """Return a mock whose .scalars().all() returns the given list."""
    result = MagicMock()
    result.scalars.return_value = MagicMock(all=MagicMock(return_value=scalars_all))
    return result


# ---------------------------------------------------------------------------
# get_telemetry_counters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_counters_empty():
    from src.telemetry_store import get_telemetry_counters

    session = _make_session()
    session.execute = AsyncMock(return_value=_exec_result([]))
    result = await get_telemetry_counters(session)
    assert result == {}


@pytest.mark.asyncio
async def test_get_counters_returns_name_value_map():
    from src.telemetry_store import get_telemetry_counters

    session = _make_session()
    session.execute = AsyncMock(
        return_value=_exec_result([_counter("req_total", 10), _counter("err_total", 2)])
    )
    result = await get_telemetry_counters(session)
    assert result == {"req_total": 10, "err_total": 2}


# ---------------------------------------------------------------------------
# get_telemetry_histograms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_histograms_empty():
    from src.telemetry_store import get_telemetry_histograms

    session = _make_session()
    session.execute = AsyncMock(return_value=_exec_result([]))
    result = await get_telemetry_histograms(session)
    assert result == {}


@pytest.mark.asyncio
async def test_get_histograms_returns_structured_map():
    from src.telemetry_store import get_telemetry_histograms

    h = _histogram("latency_ms", sum_=100.0, count=5, buckets=[10, 50, 100], counts=[1, 3, 1])
    session = _make_session()
    session.execute = AsyncMock(return_value=_exec_result([h]))
    result = await get_telemetry_histograms(session)
    assert "latency_ms" in result
    assert result["latency_ms"]["sum"] == 100.0
    assert result["latency_ms"]["count"] == 5
    assert result["latency_ms"]["buckets"] == [10, 50, 100]
    assert result["latency_ms"]["counts"] == [1, 3, 1]


# ---------------------------------------------------------------------------
# upsert_telemetry_metrics — counters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_empty_counters_and_histograms_commits():
    from src.telemetry_store import upsert_telemetry_metrics

    session = _make_session()
    await upsert_telemetry_metrics(session, {}, {})
    session.commit.assert_awaited_once()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_creates_new_counter():
    from src.telemetry_store import upsert_telemetry_metrics

    session = _make_session()
    # No existing counters returned
    session.execute = AsyncMock(return_value=_exec_result([]))

    await upsert_telemetry_metrics(session, {"req_total": 5}, {})
    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert added.name == "req_total"
    assert added.value == 5


@pytest.mark.asyncio
async def test_upsert_updates_existing_counter():
    from src.telemetry_store import upsert_telemetry_metrics

    existing = _counter("req_total", 3)
    session = _make_session()
    session.execute = AsyncMock(return_value=_exec_result([existing]))

    await upsert_telemetry_metrics(session, {"req_total": 10}, {})
    assert existing.value == 10
    session.add.assert_not_called()


# ---------------------------------------------------------------------------
# upsert_telemetry_metrics — histograms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_creates_new_histogram():
    from src.telemetry_store import upsert_telemetry_metrics

    session = _make_session()
    session.execute = AsyncMock(return_value=_exec_result([]))

    payload = {"latency_ms": {"sum": 50.0, "count": 2, "buckets": [10, 100], "counts": [1, 1]}}
    await upsert_telemetry_metrics(session, {}, payload)
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_updates_existing_histogram():
    from src.telemetry_store import upsert_telemetry_metrics

    existing = _histogram("latency_ms", sum_=10.0, count=1, buckets=[10], counts=[1])
    session = _make_session()
    session.execute = AsyncMock(return_value=_exec_result([existing]))

    payload = {"latency_ms": {"sum": 99.0, "count": 9, "buckets": [10, 100], "counts": [5, 4]}}
    await upsert_telemetry_metrics(session, {}, payload)
    assert existing.sum == 99.0
    assert existing.count == 9


@pytest.mark.asyncio
async def test_upsert_both_counters_and_histograms():
    from src.telemetry_store import upsert_telemetry_metrics

    session = _make_session()
    # Two separate execute calls: one for counters, one for histograms
    session.execute = AsyncMock(side_effect=[_exec_result([]), _exec_result([])])

    counters = {"req": 1}
    histograms = {"lat": {"sum": 1.0, "count": 1, "buckets": [], "counts": []}}
    await upsert_telemetry_metrics(session, counters, histograms)
    assert session.add.call_count == 2
    session.commit.assert_awaited_once()
