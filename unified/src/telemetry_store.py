from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import TelemetryCounter, TelemetryHistogram


async def get_telemetry_counters(session: AsyncSession) -> dict[str, int]:
    """Load all persisted counters from the database."""
    result = await session.execute(select(TelemetryCounter))
    return {counter.name: counter.value for counter in result.scalars().all()}


async def get_telemetry_histograms(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """Load all persisted histograms from the database."""
    result = await session.execute(select(TelemetryHistogram))
    return {
        histogram.name: {
            "sum": histogram.sum,
            "count": histogram.count,
            "buckets": histogram.buckets,
            "counts": histogram.counts,
        }
        for histogram in result.scalars().all()
    }


async def upsert_telemetry_metrics(
    session: AsyncSession,
    counters: dict[str, int],
    histograms: dict[str, dict[str, Any]],
) -> None:
    """Persist telemetry state with a single transaction per flush."""
    counter_rows = (
        await session.execute(
            select(TelemetryCounter).where(TelemetryCounter.name.in_(list(counters.keys())))
        )
        if counters
        else None
    )
    existing_counters = {
        counter.name: counter for counter in counter_rows.scalars().all()
    } if counter_rows else {}

    for name, value in counters.items():
        counter = existing_counters.get(name)
        if counter is None:
            session.add(TelemetryCounter(name=name, value=value))
        else:
            counter.value = value

    histogram_rows = (
        await session.execute(
            select(TelemetryHistogram).where(TelemetryHistogram.name.in_(list(histograms.keys())))
        )
        if histograms
        else None
    )
    existing_histograms = {
        histogram.name: histogram for histogram in histogram_rows.scalars().all()
    } if histogram_rows else {}

    for name, payload in histograms.items():
        histogram = existing_histograms.get(name)
        if histogram is None:
            session.add(
                TelemetryHistogram(
                    name=name,
                    sum=float(payload["sum"]),
                    count=int(payload["count"]),
                    buckets=list(payload["buckets"]),
                    counts=list(payload["counts"]),
                )
            )
        else:
            histogram.sum = float(payload["sum"])
            histogram.count = int(payload["count"])
            histogram.buckets = list(payload["buckets"])
            histogram.counts = list(payload["counts"])

    await session.commit()
