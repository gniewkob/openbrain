"""
OpenBrain Unified v2.0 — FastAPI Memory Service.

REST API for the unified memory store.
Runs in Docker on port 80 (mapped to 7010 externally).
"""

from __future__ import annotations

import structlog
from fastapi.responses import PlainTextResponse

from .app_factory import create_app
from .auth import PUBLIC_EXPOSURE
from .db import AsyncSessionLocal
from .lifespan import lifespan
from .middleware import MetricsMiddleware, RequestIDMiddleware
from .telemetry_gauges import refresh_memory_gauges
from .api.v1 import health_router, memory_router, obsidian_router
from .telemetry import render_prometheus_metrics

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)
log = structlog.get_logger()

# Backwards-compatible module alias
PUBLIC_MODE = PUBLIC_EXPOSURE

app = create_app(lifespan=lifespan)

# Middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(MetricsMiddleware)

# Health checks (unversioned, at root)
app.include_router(health_router)

# API V1 Routes
app.include_router(health_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")
app.include_router(obsidian_router, prefix="/api/v1")


@app.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
async def prometheus_metrics() -> str:
    # Keep active memory gauges aligned with DB truth on every scrape.
    try:
        async with AsyncSessionLocal() as session:
            await refresh_memory_gauges(session)
    except Exception as exc:
        log.error("metrics_gauge_refresh_failed", error=str(exc))
    return render_prometheus_metrics()


@app.get("/")
async def root():
    return {
        "service": "OpenBrain Unified",
        "version": "2.0",
        "status": "active",
        "public_exposure": PUBLIC_EXPOSURE,
    }
