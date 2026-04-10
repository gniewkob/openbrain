from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.telemetry_gauges import build_memory_gauges, refresh_memory_gauges


def test_build_memory_gauges_uses_active_status_as_source_of_truth() -> None:
    gauges = build_memory_gauges(
        status_counts={"active": 34, "superseded": 1},
        domain_status_counts={
            "build": {"active": 31},
            "corporate": {"active": 3},
            "personal": {"active": 0},
        },
    )
    assert gauges == {
        "active_memories_total": 34.0,
        "active_memories_build_total": 31.0,
        "active_memories_corporate_total": 3.0,
        "active_memories_personal_total": 0.0,
    }


@pytest.mark.asyncio
async def test_refresh_memory_gauges_sets_all_active_memory_metrics(monkeypatch) -> None:
    session = AsyncMock()

    async def fake_get_memory_status_counts(_session):
        return {"active": 10}

    async def fake_get_memory_domain_status_counts(_session):
        return {
            "build": {"active": 8},
            "corporate": {"active": 2},
            "personal": {"active": 0},
        }

    captured: dict[str, float] = {}

    def fake_set_gauge_metric(name: str, value: float) -> None:
        captured[name] = value

    monkeypatch.setattr(
        "src.telemetry_gauges.get_memory_status_counts", fake_get_memory_status_counts
    )
    monkeypatch.setattr(
        "src.telemetry_gauges.get_memory_domain_status_counts",
        fake_get_memory_domain_status_counts,
    )
    monkeypatch.setattr("src.telemetry_gauges.set_gauge_metric", fake_set_gauge_metric)

    gauges = await refresh_memory_gauges(session)
    assert gauges == {
        "active_memories_total": 10.0,
        "active_memories_build_total": 8.0,
        "active_memories_corporate_total": 2.0,
        "active_memories_personal_total": 0.0,
    }
    assert captured == gauges
