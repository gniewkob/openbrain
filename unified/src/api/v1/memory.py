"""V1 Memory API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import require_auth, get_subject, get_tenant_id, is_privileged_user
from ...db import get_session
from ...memory_reads import find_memories_v1, get_grounding_pack, get_memory_as_record
from ...memory_writes import handle_memory_write, handle_memory_write_many
from ...schemas import (
    MemoryFindRequest,
    MemoryGetContextRequest,
    MemoryGetContextResponse,
    MemoryRecord,
    MemoryWriteManyRequest,
    MemoryWriteManyResponse,
    MemoryWriteRequest,
    MemoryWriteResponse,
)
from ...telemetry import incr_metric

# PUBLIC_MODE is imported from auth module
from ...auth import PUBLIC_EXPOSURE as PUBLIC_MODE

# Security imports
from ...security import (
    enforce_domain_access,
    enforce_memory_access,
    apply_owner_scope,
    resolve_owner_for_write,
    resolve_tenant_for_write,
    _is_scoped_user,
    _effective_domain_scope,
    _record_access_denied,
)

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("/write", response_model=MemoryWriteResponse)
async def v1_write(
    req: MemoryWriteRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryWriteResponse:
    """Write a single memory record."""
    enforce_domain_access(_user, req.record.domain, "write")
    req.record.owner = resolve_owner_for_write(_user, req.record.owner)
    req.record.tenant_id = resolve_tenant_for_write(_user, req.record.tenant_id)
    if not req.record.match_key:
        incr_metric("duplicate_risk_writes_total")
    result = await handle_memory_write(session, req, actor=_user.get("sub", "agent"))
    if result.status == "created":
        incr_metric("memories_created_total")
    elif result.status == "updated":
        incr_metric("memories_updated_total")
    elif result.status == "versioned":
        incr_metric("memories_versioned_total")
    elif result.status == "skipped":
        incr_metric("memories_skipped_total")
    return result


@router.post("/write-many", response_model=MemoryWriteManyResponse)
async def v1_write_many(
    req: MemoryWriteManyRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryWriteManyResponse:
    """Write multiple memory records in batch."""
    for record in req.records:
        enforce_domain_access(_user, record.domain, "write")
        record.owner = resolve_owner_for_write(_user, record.owner)
        record.tenant_id = resolve_tenant_for_write(_user, record.tenant_id)
    result = await handle_memory_write_many(
        session, req, actor=_user.get("sub", "agent")
    )
    incr_metric("bulk_batches_total")
    incr_metric("bulk_records_total", len(req.records))
    for key in ("created", "updated", "versioned", "skipped", "failed"):
        if result.summary.get(key):
            incr_metric(f"memories_{key}_total", result.summary[key])
    return result


@router.post("/find")
async def v1_find(
    req: MemoryFindRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> list[dict[str, Any]]:
    """Find memories with filters."""
    req.filters = apply_owner_scope(_user, req.filters)
    hits = await find_memories_v1(session, req)
    incr_metric("search_requests_total")
    if not hits:
        incr_metric("search_zero_hit_total")
    return [{"record": rec, "score": score} for rec, score in hits]


@router.post("/get-context")
async def v1_get_context(
    req: MemoryGetContextRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryGetContextResponse:
    """Get context/grounding pack for AI queries."""
    if req.domain:
        enforce_domain_access(_user, req.domain, "read")
    elif PUBLIC_MODE and _is_scoped_user(_user):
        # domain=None → context spans all domains; ensure user has at least
        # one read grant.
        allowed = _effective_domain_scope(_user, "read")
        if not allowed and not is_privileged_user(_user):
            _record_access_denied("domain")
            raise HTTPException(
                status_code=403,
                detail="Read access denied: no domain grants configured",
            )
    if _is_scoped_user(_user) and not get_tenant_id(_user):
        owner = get_subject(_user)
    else:
        owner = None
    tenant_id = get_tenant_id(_user) if _is_scoped_user(_user) else None
    response = await get_grounding_pack(session, req, owner=owner, tenant_id=tenant_id)
    incr_metric("get_context_requests_total")
    return response


@router.get("/{memory_id}")
async def v1_get(
    memory_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryRecord:
    """Retrieve a single memory by ID."""
    record, memory_out = await get_memory_as_record(session, memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    enforce_domain_access(_user, memory_out.domain, "read")
    enforce_memory_access(_user, memory_out)
    return record
