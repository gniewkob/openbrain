from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

import structlog

from .db import AsyncSessionLocal
from .embed import close_embedding_client
from .telemetry import (
    bulk_load_histograms,
    bulk_load_metrics,
    get_metrics_snapshot,
)
from .telemetry_store import (
    get_telemetry_counters,
    get_telemetry_histograms,
    upsert_telemetry_metrics,
)

log = structlog.get_logger()


async def periodic_telemetry_sync() -> None:
    """Periodically flush in-memory telemetry to PostgreSQL."""
    while True:
        await asyncio.sleep(60)
        try:
            snapshot = get_metrics_snapshot()
            async with AsyncSessionLocal() as session:
                await upsert_telemetry_metrics(
                    session,
                    counters=snapshot["counters"],
                    histograms=snapshot["histograms"],
                )
                log.info(
                    "telemetry_state_synced",
                    counter_count=len(snapshot["counters"]),
                    histogram_count=len(snapshot["histograms"]),
                )
        except Exception as exc:
            log.error("telemetry_sync_failed", error=str(exc))


@asynccontextmanager
async def lifespan(app):
    del app
    try:
        async with AsyncSessionLocal() as session:
            persisted_counters = await get_telemetry_counters(session)
            persisted_histograms = await get_telemetry_histograms(session)
            if persisted_counters:
                bulk_load_metrics(persisted_counters)
            if persisted_histograms:
                bulk_load_histograms(persisted_histograms)
            if persisted_counters or persisted_histograms:
                log.info(
                    "telemetry_state_loaded",
                    counter_count=len(persisted_counters),
                    histogram_count=len(persisted_histograms),
                )
    except Exception as exc:
        log.error("telemetry_load_failed", error=str(exc))

    sync_task = asyncio.create_task(periodic_telemetry_sync())
    yield

    sync_task.cancel()
    with suppress(asyncio.CancelledError):
        await sync_task

    try:
        snapshot = get_metrics_snapshot()
        async with AsyncSessionLocal() as session:
            await upsert_telemetry_metrics(
                session,
                counters=snapshot["counters"],
                histograms=snapshot["histograms"],
            )
            log.info("telemetry_final_flush_complete")
    except Exception as exc:
        log.error("telemetry_final_flush_failed", error=str(exc))

    try:
        await close_embedding_client()
    except Exception as exc:
        log.error("embedding_client_shutdown_failed", error=str(exc))
