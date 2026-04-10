"""V1 Memory API endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import (
    require_auth,
    get_subject,
    get_tenant_id,
    is_privileged_user,
    get_policy_registry,
    set_policy_registry,
)
from ...db import get_session
from ...memory_reads import (
    get_memory_as_record,
    export_memories,
    get_memory,
    get_test_data_hygiene_report,
    list_maintenance_reports,
    get_maintenance_report,
    sync_check,
)
from ...use_cases.memory import (
    cleanup_build_test_data as cleanup_build_test_data_use_case,
    store_memory as handle_memory_write,
    store_memories_many as handle_memory_write_many,
    search_memories as find_memories_v1,
    get_memory_context as get_grounding_pack,
    delete_memory,
    update_memory,
    run_maintenance,
    upsert_memories_bulk,
)
from ...schemas import (
    MemoryFindRequest,
    MemoryGetContextRequest,
    MemoryGetContextResponse,
    MemoryRecord,
    MemoryWriteManyRequest,
    MemoryWriteManyResponse,
    MemoryWriteRequest,
    MemoryWriteResponse,
    MaintenanceRequest,
    MaintenanceReport,
    MaintenanceReportEntry,
    MaintenanceReportDetail,
    ExportRequest,
    PolicyRegistry,
    SyncCheckRequest,
    SyncCheckResponse,
    MemoryUpdate,
    MemoryUpsertItem,
    BulkUpsertResult,
    BuildTestDataCleanupRequest,
    BuildTestDataCleanupResponse,
    TestDataHygieneReport,
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
    require_admin,
    _is_scoped_user,
    _effective_domain_scope,
    _record_access_denied,
    hide_memory_access_denied,
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
    try:
        hits = await find_memories_v1(session, req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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


@router.patch("/{memory_id}", response_model=MemoryRecord)
async def v1_update(
    memory_id: str,
    data: MemoryUpdate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryRecord:
    """Update an existing memory by ID (in-place for build/personal, new version for corporate)."""
    record, memory_out = await get_memory_as_record(session, memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    enforce_domain_access(_user, memory_out.domain, "write")
    enforce_memory_access(_user, memory_out)
    actor = get_subject(_user)
    # Governance hardening: request-level updated_by is compatibility metadata only.
    # The authenticated subject is authoritative for audit actor identity.
    safe_data = data.model_copy(update={"updated_by": actor})
    updated = await update_memory(session, memory_id, safe_data, actor=actor)
    if updated is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    updated_record, _ = await get_memory_as_record(session, updated.id)
    return updated_record


# ---------------------------------------------------------------------------
# Admin / Operations Endpoints
# ---------------------------------------------------------------------------


@router.post("/maintain", response_model=MaintenanceReport)
async def maintain(
    req: MaintenanceRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MaintenanceReport:
    """Run maintenance tasks (dedup, normalization)."""
    require_admin(_user)
    report = await run_maintenance(session, req, actor=_user.get("sub", "agent"))
    incr_metric("maintain_runs_total")
    return report


@router.get("/maintain/reports", response_model=list[MaintenanceReportEntry])
async def maintain_reports(
    limit: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> list[MaintenanceReportEntry]:
    """List recent maintenance reports."""
    require_admin(_user)
    return await list_maintenance_reports(session, limit=limit)


@router.get("/maintain/reports/{report_id}", response_model=MaintenanceReportDetail)
async def maintain_report_detail(
    report_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MaintenanceReportDetail:
    """Get detailed maintenance report."""
    require_admin(_user)
    report = await get_maintenance_report(session, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Maintenance report not found")
    return report


@router.get("/admin/test-data/report", response_model=TestDataHygieneReport)
async def test_data_hygiene_report(
    sample_limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> TestDataHygieneReport:
    """Return diagnostic report for records hidden by test-data policy."""
    require_admin(_user)
    return await get_test_data_hygiene_report(session, sample_limit=sample_limit)


@router.post(
    "/admin/test-data/cleanup-build",
    response_model=BuildTestDataCleanupResponse,
)
async def cleanup_build_test_data(
    req: BuildTestDataCleanupRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> BuildTestDataCleanupResponse:
    """Cleanup build-domain test data with explicit dry-run by default."""
    require_admin(_user)
    return await cleanup_build_test_data_use_case(
        session,
        dry_run=req.dry_run,
        limit=req.limit,
        actor=get_subject(_user),
    )


@router.post("/export")
async def v1_export(
    req: ExportRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> Any:
    """Export memories in JSON/JSONL format."""
    require_admin(_user)
    for memory_id in req.ids:
        mem = await get_memory(session, memory_id)
        if mem is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        try:
            enforce_domain_access(_user, mem.domain, "read")
            enforce_memory_access(_user, mem)
        except HTTPException as exc:
            raise hide_memory_access_denied(exc) from exc

    incr_metric("exports_total")
    records = await export_memories(session, req.ids, role="admin")
    if req.format == "jsonl":
        content = "\n".join(json.dumps(r, default=str) for r in records) + "\n"
        return Response(content=content, media_type="application/x-ndjson")
    return records


@router.get("/security/policy-registry", response_model=PolicyRegistry)
async def read_policy_registry(
    _user: dict = Depends(require_auth),
) -> PolicyRegistry:
    """Read the global security policy registry."""
    require_admin(_user)
    return PolicyRegistry(**get_policy_registry())


@router.post("/security/policy-registry", response_model=PolicyRegistry)
async def update_policy_registry(
    registry: PolicyRegistry,
    _user: dict = Depends(require_auth),
) -> PolicyRegistry:
    """Update the global security policy registry."""
    require_admin(_user)
    return PolicyRegistry(**await set_policy_registry(registry.model_dump()))


@router.delete("/{memory_id}")
async def v1_delete(
    memory_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> dict:
    """Delete a build/personal memory. Corporate memories return 403."""
    mem = await get_memory(session, memory_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    enforce_domain_access(_user, mem.domain, "write")
    enforce_memory_access(_user, mem)
    try:
        deleted = await delete_memory(session, memory_id, actor=get_subject(_user))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True, "id": memory_id}


@router.post("/sync-check", response_model=SyncCheckResponse)
async def v1_sync_check(
    req: SyncCheckRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> SyncCheckResponse:
    """Check if a memory exists and whether its content hash is current."""
    try:
        result = await sync_check(
            session,
            memory_id=req.memory_id,
            match_key=req.match_key,
            obsidian_ref=req.obsidian_ref,
            file_hash=req.file_hash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SyncCheckResponse(**result)


@router.post("/bulk-upsert", response_model=BulkUpsertResult)
async def v1_bulk_upsert(
    items: list[MemoryUpsertItem],
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> BulkUpsertResult:
    """Idempotent bulk upsert. Every item must have a match_key."""
    for item in items:
        enforce_domain_access(_user, item.domain, "write")
    try:
        result = await upsert_memories_bulk(session, items)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result
