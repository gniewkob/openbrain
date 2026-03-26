"""
OpenBrain Unified v2.0 — FastAPI Memory Service.

REST API for the unified memory store.
Runs in Docker on port 80 (mapped to 7010 externally).
"""
from __future__ import annotations

import os
import uuid
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import require_auth
from .crud import (
    delete_memory,
    export_memories,
    find_memories_v1,
    get_grounding_pack,
    get_memory,
    handle_memory_write,
    handle_memory_write_many,
    list_memories,
    run_maintenance,
    search_memories,
    store_memories_bulk,
    store_memory,
    sync_check,
    update_memory,
    upsert_memories_bulk,
)
from .db import AsyncSessionLocal, get_session
from .schemas import (
    BulkUpsertResult,
    ExportRequest,
    MaintenanceReport,
    MaintenanceRequest,
    MemoryCreate,
    MemoryFindRequest,
    MemoryGetContextRequest,
    MemoryGetContextResponse,
    MemoryOut,
    MemoryRecord,
    MemoryUpdate,
    MemoryUpsertItem,
    MemoryWriteManyRequest,
    MemoryWriteManyResponse,
    MemoryWriteRequest,
    MemoryWriteResponse,
    SearchRequest,
    SearchResult,
)

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

# ---------------------------------------------------------------------------
# App Initialization
# ---------------------------------------------------------------------------

_public_base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
_servers = [{"url": _public_base}] if _public_base else []

app = FastAPI(
    title="OpenBrain Unified Memory Service",
    version="2.0.0",
    description=(
        "Unified memory store with domain-aware governance. "
        "Corporate: append-only versioning + audit trail. "
        "Build/Personal: mutable + deletable."
    ),
    servers=_servers or None,
    docs_url="/docs",
    redoc_url=None,
)

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(request_id=req_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        structlog.contextvars.clear_contextvars()
        return response

app.add_middleware(RequestIDMiddleware)

# ---------------------------------------------------------------------------
# API V1 (Canonical)
# ---------------------------------------------------------------------------

@app.post("/api/v1/memory/write", response_model=MemoryWriteResponse)
async def v1_write(
    req: MemoryWriteRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryWriteResponse:
    return await handle_memory_write(session, req, actor=_user.get("sub", "agent"))

@app.post("/api/v1/memory/write-many", response_model=MemoryWriteManyResponse)
async def v1_write_many(
    req: MemoryWriteManyRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryWriteManyResponse:
    return await handle_memory_write_many(session, req, actor=_user.get("sub", "agent"))

@app.post("/api/v1/memory/find", response_model=list[dict[str, Any]])
async def v1_find(
    req: MemoryFindRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> list[dict[str, Any]]:
    hits = await find_memories_v1(session, req)
    return [{"record": rec, "score": score} for rec, score in hits]

@app.post("/api/v1/memory/get-context", response_model=MemoryGetContextResponse)
async def v1_get_context(
    req: MemoryGetContextRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryGetContextResponse:
    return await get_grounding_pack(session, req)

# ---------------------------------------------------------------------------
# Well-Known Discovery (for ChatGPT MCP)
# ---------------------------------------------------------------------------

@app.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource() -> dict:
    """RFC 9470 — tells ChatGPT where to find the OAuth server."""
    return {
        "resource": _public_base or "http://localhost:7010",
        "authorization_servers": [
            os.environ.get("OIDC_ISSUER_URL", "").rstrip("/")
        ],
    }

@app.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server() -> dict:
    """OAuth Authorization Server Metadata (RFC 8414)."""
    issuer = os.environ.get("OIDC_ISSUER_URL", "").rstrip("/")
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/oauth/token",
        "registration_endpoint": f"{issuer}/oidc/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
    }

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok", "service": "openbrain-unified", "db": "ok"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "service": "openbrain-unified", "db": "error"},
        )

# ---------------------------------------------------------------------------
# API Routes (CRUD)
# ---------------------------------------------------------------------------

@app.post("/api/memories", response_model=MemoryOut, status_code=201)
async def create_memory(
    data: MemoryCreate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryOut:
    return await store_memory(session, data)

@app.post("/api/memories/bulk", response_model=list[MemoryOut], status_code=201)
async def create_memories_bulk(
    data: list[MemoryCreate],
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> list[MemoryOut]:
    if not data:
        raise HTTPException(status_code=422, detail="Empty list")
    return await store_memories_bulk(session, data)

@app.post("/api/memories/bulk-upsert", response_model=BulkUpsertResult, status_code=200)
async def bulk_upsert_memories(
    data: list[MemoryUpsertItem],
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> BulkUpsertResult:
    return await upsert_memories_bulk(session, data)

@app.get("/api/memories/{memory_id}", response_model=MemoryOut)
async def read_memory(
    memory_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryOut:
    memory = await get_memory(session, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory

@app.get("/api/memories", response_model=list[MemoryOut])
async def read_memories(
    domain: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> list[MemoryOut]:
    return await list_memories(session, {"domain": domain} if domain else {}, limit)

@app.post("/api/memories/search", response_model=list[SearchResult])
async def search(
    req: SearchRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> list[SearchResult]:
    rows = await search_memories(session, req)
    return [SearchResult(memory=mem, score=score) for mem, score in rows]

@app.put("/api/memories/{memory_id}", response_model=MemoryOut)
async def update(
    memory_id: str,
    data: MemoryUpdate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryOut:
    memory = await update_memory(session, memory_id, data)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory

@app.delete("/api/memories/{memory_id}", status_code=204)
async def delete(
    memory_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> None:
    try:
        deleted = await delete_memory(session, memory_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")

@app.post("/api/memories/sync-check")
async def check_sync_endpoint(
    obsidian_ref: str,
    file_hash: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> dict:
    return await sync_check(session, obsidian_ref, file_hash)

@app.post("/api/admin/maintain", response_model=MaintenanceReport)
async def maintain(
    req: MaintenanceRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MaintenanceReport:
    return await run_maintenance(session, req)

@app.post("/api/memories/export")
async def export(
    req: ExportRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> list[dict]:
    return await export_memories(session, req.ids)
