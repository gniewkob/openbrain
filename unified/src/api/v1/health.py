"""Health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text

from ...auth import require_auth
from ...db import AsyncSessionLocal
from fastapi.responses import JSONResponse
import structlog

router = APIRouter(tags=["health"])
log = structlog.get_logger()


@router.get("/healthz")
async def healthz() -> dict:
    """Basic health check - always returns OK."""
    return {"status": "ok", "service": "openbrain-unified"}


@router.get("/readyz")
async def readyz() -> dict:
    """Readiness check - verifies database connectivity."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok", "service": "openbrain-unified", "db": "ok"}
    except Exception as exc:
        log.error("readyz_db_check_failed", error=str(exc))
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "service": "openbrain-unified", "db": "error"},
        )


@router.get("/health")
async def health(
    _user: dict = Depends(require_auth),
) -> dict:
    """Detailed health check (requires authentication)."""
    return await readyz()
