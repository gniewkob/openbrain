"""Health check endpoints."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

import structlog

from ...auth import require_auth
from ...config import get_config
from ...db import AsyncSessionLocal

router = APIRouter(tags=["health"])
log = structlog.get_logger()

_VECTOR_STORE_TIMEOUT = 3.0  # seconds


async def _check_vector_store() -> str:
    """Check Ollama embedding service availability.

    Returns 'ok' if reachable within timeout, 'degraded' otherwise.
    """
    config = get_config()
    ollama_url = config.embedding.url
    model = config.embedding.model
    try:
        async with httpx.AsyncClient(timeout=_VECTOR_STORE_TIMEOUT) as client:
            r = await client.post(
                f"{ollama_url}/api/embeddings",
                json={"model": model, "prompt": "health"},
            )
        return "ok" if r.status_code == 200 else "degraded"
    except Exception:
        return "degraded"


@router.get("/healthz")
async def healthz() -> dict[str, Any]:
    """Basic health check - always returns OK."""
    return {"status": "ok", "service": "openbrain-unified"}


@router.get("/readyz", response_model=None)
async def readyz() -> JSONResponse | dict[str, Any]:
    """Readiness check - verifies database and vector store connectivity."""
    db_status = "ok"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        log.error("readyz_db_check_failed", error=str(exc))
        db_status = "degraded"

    vector_store_status = await _check_vector_store()

    overall = "ok" if db_status == "ok" else "degraded"
    payload: dict[str, Any] = {
        "status": overall,
        "service": "openbrain-unified",
        "db": db_status,
        "vector_store": vector_store_status,
    }
    if db_status != "ok":
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.get("/health", response_model=None)
async def health(
    _user: dict[str, Any] = Depends(require_auth),
) -> JSONResponse | dict[str, Any]:
    """Detailed health check (requires authentication)."""
    return await readyz()
