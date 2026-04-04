"""
OpenBrain Unified v2.0 — FastAPI Memory Service.

REST API for the unified memory store.
Runs in Docker on port 80 (mapped to 7010 externally).
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import structlog
from fastapi import Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .app_factory import create_app
from .auth import (
    PUBLIC_EXPOSURE,
    get_domain_scope,
    get_policy_registry,
    get_registry_domain_scope,
    get_subject,
    get_tenant_id,
    is_privileged_user,
    require_auth,
    set_policy_registry,
)
from .db import AsyncSessionLocal, get_session
from .lifespan import lifespan
from .middleware import MetricsMiddleware, RequestIDMiddleware
from .memory_reads import (
    export_memories,
    find_memories_v1,
    get_grounding_pack,
    get_memory,
    get_memory_as_record,
    get_memory_domain_status_counts,
    get_memory_status_counts,
    get_maintenance_report,
    list_maintenance_reports,
    list_memories,
    search_memories,
    sync_check,
)
from .memory_writes import (
    delete_memory,
    handle_memory_write,
    handle_memory_write_many,
    run_maintenance,
    store_memories_bulk,
    store_memory,
    update_memory,
    upsert_memories_bulk,
)
from .obsidian_cli import ObsidianCliAdapter, ObsidianCliError, note_to_memory_write_record
from .routes_crud import register_crud_routes
from .api.v1 import health_router, memory_router, obsidian_router
from .routes_ops import register_ops_routes
from .routes_v1 import register_v1_routes
from .obsidian_sync import BidirectionalSyncEngine, ObsidianChangeTracker, SyncStrategy
from .schemas import (
    BulkUpsertResult,
    ExportRequest,
    MaintenanceReport,
    MaintenanceReportDetail,
    MaintenanceReportEntry,
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
    ObsidianBidirectionalSyncRequest,
    ObsidianBidirectionalSyncResponse,
    ObsidianCollectionRequest,
    ObsidianSyncChange,
    ObsidianCollectionResponse,
    ObsidianExportItem,
    ObsidianExportRequest,
    ObsidianExportResponse,
    ObsidianNoteResponse,
    ObsidianReadRequest,
    ObsidianSyncRequest,
    ObsidianSyncResponse,
    ObsidianSyncStatus,
    ObsidianWriteRequest,
    ObsidianWriteResponse,
    PolicyRegistry,
    SearchRequest,
    SearchResult,
    SyncCheckRequest,
    SyncCheckResponse,
)
from .telemetry import (
    get_metrics_snapshot,
    incr_metric,
    render_prometheus_metrics,
    set_gauge_metric,
)
from pydantic import ValidationError

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

# Backwards-compatible module alias used by existing tests and local patches.
# Semantics now follow effective public exposure, not only PUBLIC_MODE=true.
PUBLIC_MODE = PUBLIC_EXPOSURE

# ---------------------------------------------------------------------------
# App Initialization
# ---------------------------------------------------------------------------

_public_base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
app = create_app(public_base_url=_public_base, lifespan=lifespan)


def _count_policy_skips_by_reason(actions: list[Any]) -> dict[str, int]:
    counters = {
        "delete": 0,
        "dedup": 0,
        "owner_normalization": 0,
        "link_repair": 0,
    }
    for action in actions:
        if getattr(action, "action", None) != "policy_skip":
            continue
        detail = (getattr(action, "detail", "") or "").lower()
        if "dedup" in detail:
            counters["dedup"] += 1
        elif "owner normalization" in detail:
            counters["owner_normalization"] += 1
        elif "link repair" in detail:
            counters["link_repair"] += 1
    return counters


ALERT_THRESHOLDS: dict[str, dict[str, float]] = {
    "policy_skip_per_maintain_run_ratio": {"watch": 0.25, "elevated": 1.0},
    "duplicate_candidates_per_maintain_run_ratio": {"watch": 1.0, "elevated": 5.0},
    "search_zero_hit_ratio": {"watch": 0.05, "elevated": 0.15},
}


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _refresh_operational_gauges() -> dict[str, float]:
    counters = get_metrics_snapshot()["counters"]
    derived = {
        "policy_skip_per_maintain_run_ratio": _safe_ratio(
            int(counters.get("policy_skip_total", 0)),
            int(counters.get("maintain_runs_total", 0)),
        ),
        "duplicate_candidates_per_maintain_run_ratio": _safe_ratio(
            int(counters.get("duplicate_candidates_total", 0)),
            int(counters.get("maintain_runs_total", 0)),
        ),
        "versioned_to_updated_ratio": _safe_ratio(
            int(counters.get("memories_versioned_total", 0)),
            int(counters.get("memories_updated_total", 0)),
        ),
        "search_zero_hit_ratio": _safe_ratio(
            int(counters.get("search_zero_hit_total", 0)),
            int(counters.get("search_requests_total", 0)),
        ),
    }
    health_status = _compute_operational_health(derived)
    derived["operational_health_status"] = float(health_status)
    for name, value in derived.items():
        set_gauge_metric(name, value)
    for metric_name, thresholds in ALERT_THRESHOLDS.items():
        set_gauge_metric(f"{metric_name}_watch_threshold", thresholds["watch"])
        set_gauge_metric(f"{metric_name}_elevated_threshold", thresholds["elevated"])
    return derived


def _compute_operational_health(summary: dict[str, float]) -> int:
    if (
        summary["policy_skip_per_maintain_run_ratio"] >= ALERT_THRESHOLDS["policy_skip_per_maintain_run_ratio"]["elevated"]
        or summary["duplicate_candidates_per_maintain_run_ratio"] >= ALERT_THRESHOLDS["duplicate_candidates_per_maintain_run_ratio"]["elevated"]
        or summary["search_zero_hit_ratio"] >= ALERT_THRESHOLDS["search_zero_hit_ratio"]["elevated"]
    ):
        return 2
    if (
        summary["policy_skip_per_maintain_run_ratio"] >= ALERT_THRESHOLDS["policy_skip_per_maintain_run_ratio"]["watch"]
        or summary["duplicate_candidates_per_maintain_run_ratio"] >= ALERT_THRESHOLDS["duplicate_candidates_per_maintain_run_ratio"]["watch"]
        or summary["search_zero_hit_ratio"] >= ALERT_THRESHOLDS["search_zero_hit_ratio"]["watch"]
    ):
        return 1
    return 0


def _build_operational_summary() -> dict[str, float | str | dict[str, dict[str, float]]]:
    counters = get_metrics_snapshot()["counters"]
    maintain_runs = int(counters.get("maintain_runs_total", 0))
    policy_skips = int(counters.get("policy_skip_total", 0))
    duplicate_candidates = int(counters.get("duplicate_candidates_total", 0))
    summary: dict[str, float | str | dict[str, dict[str, float]]] = {
        "policy_skip_per_maintain_run_ratio": _safe_ratio(policy_skips, maintain_runs),
        "duplicate_candidates_per_maintain_run_ratio": _safe_ratio(duplicate_candidates, maintain_runs),
        "versioned_to_updated_ratio": _safe_ratio(
            int(counters.get("memories_versioned_total", 0)),
            int(counters.get("memories_updated_total", 0)),
        ),
        "search_zero_hit_ratio": _safe_ratio(
            int(counters.get("search_zero_hit_total", 0)),
            int(counters.get("search_requests_total", 0)),
        ),
    }
    health_status = _compute_operational_health({
        "policy_skip_per_maintain_run_ratio": float(summary["policy_skip_per_maintain_run_ratio"]),
        "duplicate_candidates_per_maintain_run_ratio": float(summary["duplicate_candidates_per_maintain_run_ratio"]),
        "versioned_to_updated_ratio": float(summary["versioned_to_updated_ratio"]),
        "search_zero_hit_ratio": float(summary["search_zero_hit_ratio"]),
    })
    if health_status == 2:
        health = "elevated"
    elif health_status == 1:
        health = "watch"
    else:
        health = "normal"
    return {"health": health, "health_status": float(health_status), "thresholds": ALERT_THRESHOLDS, **summary}


def _is_scoped_user(user: dict[str, Any]) -> bool:
    return PUBLIC_MODE and not is_privileged_user(user)


def _record_access_denied(reason: str) -> None:
    incr_metric("access_denied_total")
    incr_metric(f"access_denied_{reason}_total")


def _require_admin(user: dict[str, Any]) -> None:
    if not PUBLIC_MODE:
        return
    if not is_privileged_user(user):
        _record_access_denied("admin")
        raise HTTPException(status_code=403, detail="Admin privileges required")


def _effective_domain_scope(user: dict[str, Any], action: str) -> set[str]:
    subject = get_subject(user)
    tenant_id = get_tenant_id(user)
    claim_scope = get_domain_scope(user, action)
    registry_scope = get_registry_domain_scope(subject, tenant_id, action)
    if claim_scope and registry_scope:
        return claim_scope & registry_scope
    return claim_scope or registry_scope


def _enforce_domain_access(user: dict[str, Any], domain: str, action: str) -> None:
    if not PUBLIC_MODE:
        return
    allowed = _effective_domain_scope(user, action)
    if not allowed:
        # No domain scope configured — privileged users get full access, others are denied.
        if is_privileged_user(user):
            return
        _record_access_denied("domain")
        raise HTTPException(status_code=403, detail=f"{action.capitalize()} access denied for domain '{domain}'")
    # Fail-closed: deny unless there is an explicit non-empty grant that includes
    # this domain. An empty allowed set means no grants were configured for this
    # user+action pair, not "all domains permitted" (C1 fix).
    if domain.lower() not in allowed:
        _record_access_denied("domain")
        raise HTTPException(status_code=403, detail=f"{action.capitalize()} access denied for domain '{domain}'")


def _resolve_owner_for_write(user: dict[str, Any], owner: str | None) -> str:
    if not _is_scoped_user(user):
        return owner or ""
    if get_tenant_id(user):
        return owner or ""
    subject = get_subject(user)
    if owner and owner != subject:
        _record_access_denied("owner")
        raise HTTPException(status_code=403, detail="Cannot write records for another owner")
    return subject


def _resolve_tenant_for_write(user: dict[str, Any], tenant_id: str | None) -> str | None:
    if not _is_scoped_user(user):
        return tenant_id
    scoped_tenant = get_tenant_id(user)
    if not scoped_tenant:
        return tenant_id
    if tenant_id and tenant_id != scoped_tenant:
        _record_access_denied("tenant")
        raise HTTPException(status_code=403, detail="Cannot write records for another tenant")
    return scoped_tenant


def _apply_owner_scope(user: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
    scoped = dict(filters)
    if _is_scoped_user(user):
        allowed_read_domains = _effective_domain_scope(user, "read")
        requested = scoped.get("domain")
        if requested is None:
            if allowed_read_domains:
                scoped["domain"] = sorted(allowed_read_domains)
            # If allowed_read_domains is empty, rely on owner/tenant_id filters below
            # to limit exposure — no domain injection means all domains but only the
            # user's own records are returned.
        else:
            if allowed_read_domains:
                requested_domains = requested if isinstance(requested, list) else [requested]
                normalized = {str(domain).lower() for domain in requested_domains}
                if not normalized.issubset(allowed_read_domains):
                    _record_access_denied("domain")
                    raise HTTPException(status_code=403, detail="Read access denied for requested domain scope")
            # If no domain grants exist, we don't block the request — owner/tenant
            # scope below will still restrict the result set to the user's own records.
    if not _is_scoped_user(user):
        return scoped
    scoped_tenant = get_tenant_id(user)
    if scoped_tenant:
        scoped["tenant_id"] = scoped_tenant
        scoped.pop("owner", None)
    else:
        scoped["owner"] = get_subject(user)
    return scoped


def _enforce_memory_access(user: dict[str, Any], memory: MemoryOut) -> None:
    if not _is_scoped_user(user):
        return
    scoped_tenant = get_tenant_id(user)
    if scoped_tenant:
        if not memory.tenant_id or memory.tenant_id != scoped_tenant:
            _record_access_denied("tenant")
            raise HTTPException(status_code=404, detail="Memory not found")
        return
    subject = get_subject(user)
    if not memory.owner or memory.owner != subject:
        _record_access_denied("owner")
        raise HTTPException(status_code=404, detail="Memory not found")


def _hide_memory_access_denied(exc: HTTPException) -> HTTPException:
    if exc.status_code in {403, 404}:
        return HTTPException(status_code=404, detail="Memory not found")
    return exc

app.add_middleware(MetricsMiddleware)
app.add_middleware(RequestIDMiddleware)

# ---------------------------------------------------------------------------
# New Modular V1 Routers (Refactored)
# ---------------------------------------------------------------------------

app.include_router(health_router)
app.include_router(memory_router, prefix="/api/v1")
app.include_router(obsidian_router, prefix="/api/v1")

# ---------------------------------------------------------------------------
# Legacy API V1 (Inline - to be migrated)
# ---------------------------------------------------------------------------

async def v1_write(
    req: MemoryWriteRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryWriteResponse:
    _enforce_domain_access(_user, req.record.domain, "write")
    req.record.owner = _resolve_owner_for_write(_user, req.record.owner)
    req.record.tenant_id = _resolve_tenant_for_write(_user, req.record.tenant_id)
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

async def v1_write_many(
    req: MemoryWriteManyRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryWriteManyResponse:
    for record in req.records:
        _enforce_domain_access(_user, record.domain, "write")
        record.owner = _resolve_owner_for_write(_user, record.owner)
        record.tenant_id = _resolve_tenant_for_write(_user, record.tenant_id)
    result = await handle_memory_write_many(session, req, actor=_user.get("sub", "agent"))
    incr_metric("bulk_batches_total")
    incr_metric("bulk_records_total", len(req.records))
    for key in ("created", "updated", "versioned", "skipped", "failed"):
        if result.summary.get(key):
            incr_metric(f"memories_{key}_total", result.summary[key])
    return result

async def v1_find(
    req: MemoryFindRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> list[dict[str, Any]]:
    req.filters = _apply_owner_scope(_user, req.filters)
    hits = await find_memories_v1(session, req)
    incr_metric("search_requests_total")
    if not hits:
        incr_metric("search_zero_hit_total")
    return [{"record": rec, "score": score} for rec, score in hits]

async def v1_get_context(
    req: MemoryGetContextRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryGetContextResponse:
    if req.domain:
        _enforce_domain_access(_user, req.domain, "read")
    elif PUBLIC_MODE and _is_scoped_user(_user):
        # domain=None → context spans all domains; ensure user has at least one read grant.
        allowed = _effective_domain_scope(_user, "read")
        if not allowed and not is_privileged_user(_user):
            _record_access_denied("domain")
            raise HTTPException(status_code=403, detail="Read access denied: no domain grants configured")
    owner = get_subject(_user) if _is_scoped_user(_user) and not get_tenant_id(_user) else None
    tenant_id = get_tenant_id(_user) if _is_scoped_user(_user) else None
    response = await get_grounding_pack(session, req, owner=owner, tenant_id=tenant_id)
    incr_metric("get_context_requests_total")
    return response


async def v1_get(
    memory_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryRecord:
    """Retrieve a single memory by ID — returns canonical MemoryRecord (V1 shape)."""
    record, memory_out = await get_memory_as_record(session, memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    _enforce_domain_access(_user, memory_out.domain, "read")
    _enforce_memory_access(_user, memory_out)
    return record


async def v1_obsidian_vaults(
    _user: dict = Depends(require_auth),
) -> list[str]:
    _require_admin(_user)
    adapter = ObsidianCliAdapter()
    try:
        return await adapter.list_vaults()
    except ObsidianCliError as e:
        raise HTTPException(status_code=503, detail=str(e))


async def v1_obsidian_read_note(
    req: ObsidianReadRequest,
    _user: dict = Depends(require_auth),
) -> ObsidianNoteResponse:
    _require_admin(_user)
    adapter = ObsidianCliAdapter()
    try:
        note = await adapter.read_note(req.vault, req.path)
    except ObsidianCliError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return ObsidianNoteResponse(
        vault=note.vault,
        path=note.path,
        title=note.title,
        content=note.content,
        frontmatter=note.frontmatter,
        tags=note.tags,
        file_hash=note.file_hash,
    )


async def v1_obsidian_sync(
    req: ObsidianSyncRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> ObsidianSyncResponse:
    _require_admin(_user)
    adapter = ObsidianCliAdapter()
    try:
        if req.paths:
            resolved_paths = req.paths[: req.limit]
        else:
            resolved_paths = await adapter.list_files(req.vault, folder=req.folder, limit=req.limit)

        notes = [await adapter.read_note(req.vault, path) for path in resolved_paths]
    except ObsidianCliError as e:
        raise HTTPException(status_code=503, detail=str(e))
    records = [
        note_to_memory_write_record(
            note,
            default_domain=req.domain,
            default_entity_type=req.entity_type,
            default_owner=req.owner,
            default_tags=req.tags,
        )
        for note in notes
    ]
    result = await handle_memory_write_many(
        session,
        MemoryWriteManyRequest(records=records, write_mode="upsert"),
        actor=_user.get("sub", "obsidian-sync"),
    )
    return ObsidianSyncResponse(
        vault=req.vault,
        resolved_paths=resolved_paths,
        scanned=len(resolved_paths),
        summary=result.summary,
        results=result.results,
    )


# ---------------------------------------------------------------------------
# Obsidian Export (OpenBrain → Obsidian)
# ---------------------------------------------------------------------------

async def v1_obsidian_write_note(
    req: ObsidianWriteRequest,
    _user: dict = Depends(require_auth),
) -> ObsidianWriteResponse:
    """Write a single note to Obsidian vault."""
    _require_admin(_user)
    adapter = ObsidianCliAdapter()
    try:
        # Check if note exists
        exists = await adapter.note_exists(req.vault, req.path)
        
        note = await adapter.write_note(
            vault=req.vault,
            path=req.path,
            content=req.content,
            frontmatter=req.frontmatter,
            overwrite=req.overwrite,
        )
    except ObsidianCliError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return ObsidianWriteResponse(
        vault=note.vault,
        path=note.path,
        title=note.title,
        content=note.content,
        frontmatter=note.frontmatter,
        tags=note.tags,
        file_hash=note.file_hash,
        created=not exists,  # True if new, False if updated
    )


async def v1_obsidian_export(
    req: ObsidianExportRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> ObsidianExportResponse:
    """Export memories from OpenBrain to Obsidian notes."""
    _require_admin(_user)

    # Get memories to export
    memories: list[MemoryOut] = []
    if req.memory_ids:
        for mid in req.memory_ids:
            mem = await get_memory(session, mid)
            if mem:
                memories.append(mem)
    elif req.query:
        search_results = await search_memories(
            session,
            SearchRequest(query=req.query, top_k=req.max_items, filters={}),
        )
        memories = [mem for mem, _ in search_results]
        
        # Filter by domain if specified
        if req.domain:
            memories = [m for m in memories if m.domain == req.domain]
    else:
        raise HTTPException(status_code=422, detail="Either memory_ids or query must be provided")

    # Export to Obsidian
    adapter = ObsidianCliAdapter()
    exported: list[ObsidianExportItem] = []
    errors: list[dict[str, str]] = []

    for memory in memories:
        try:
            # Generate note path
            safe_title = _sanitize_filename(memory.title or memory.id)
            path = f"{req.folder}/{safe_title}.md" if req.folder else f"{safe_title}.md"

            # Generate content and frontmatter
            content = _memory_to_note_content(memory, req.template)
            frontmatter = _memory_to_frontmatter(memory)

            # Check if exists
            exists = await adapter.note_exists(req.vault, path)
            
            note = await adapter.write_note(
                vault=req.vault,
                path=path,
                content=content,
                frontmatter=frontmatter,
                overwrite=True,
            )
            exported.append(ObsidianExportItem(
                memory_id=memory.id,
                path=note.path,
                title=note.title,
                created=not exists,
            ))
        except Exception as e:
            log.warning("export_memory_failed", memory_id=memory.id, error=str(e))
            errors.append({"memory_id": memory.id, "error": str(e)})

    return ObsidianExportResponse(
        vault=req.vault,
        folder=req.folder,
        exported_count=len(exported),
        exported=exported,
        errors=errors,
    )


async def v1_obsidian_collection(
    req: ObsidianCollectionRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> ObsidianCollectionResponse:
    """Create a collection (index note) from memories."""
    _require_admin(_user)

    # First export memories
    export_req = ObsidianExportRequest(
        vault=req.vault,
        folder=f"{req.folder}/{req.collection_name}",
        query=req.query,
        domain=req.domain,
        max_items=req.max_items,
    )
    
    # Get memories for grouping info
    search_results = await search_memories(
        session,
        SearchRequest(query=req.query, top_k=req.max_items, filters={}),
    )
    memories = [mem for mem, _ in search_results]
    if req.domain:
        memories = [m for m in memories if m.domain == req.domain]
    
    # Export memories
    export_result = await v1_obsidian_export(export_req, session, _user)

    # Create index note
    adapter = ObsidianCliAdapter()
    try:
        index_content = _build_collection_index(
            collection_name=req.collection_name,
            query=req.query,
            exported=export_result.exported,
            memories=memories,
            group_by=req.group_by,
        )
        
        index_path = f"{req.folder}/{req.collection_name}/Index.md"
        
        await adapter.write_note(
            vault=req.vault,
            path=index_path,
            content=index_content,
            frontmatter={
                "title": req.collection_name,
                "tags": ["openbrain-collection", "index"],
                "query": req.query,
                "item_count": len(export_result.exported),
                "created_at": datetime.now().isoformat(),
            },
            overwrite=True,
        )

        return ObsidianCollectionResponse(
            collection_name=req.collection_name,
            vault=req.vault,
            folder=req.folder,
            index_path=index_path,
            exported_count=export_result.exported_count,
            exported=export_result.exported,
            errors=export_result.errors,
        )
    except ObsidianCliError as e:
        raise HTTPException(status_code=503, detail=str(e))


def _sanitize_filename(name: str) -> str:
    """Sanitize string for use as filename."""
    unsafe = '<>:"/\\|?*'
    for char in unsafe:
        name = name.replace(char, '_')
    return name[:100]  # Limit length


def _memory_to_note_content(memory: MemoryOut, template: str | None = None) -> str:
    """Convert memory to markdown note content."""
    if template:
        try:
            return template.format(
                title=memory.title or "Untitled",
                content=memory.content,
                domain=memory.domain,
                entity_type=memory.entity_type,
                created_at=memory.created_at,
                updated_at=memory.updated_at,
                owner=memory.owner,
                tags=", ".join(memory.tags),
                id=memory.id,
                version=memory.version,
            )
        except Exception:
            # Fall back to default if template fails
            pass

    # Default format
    lines = [
        f"# {memory.title or 'Untitled'}",
        "",
        f"**Domain:** {memory.domain}",
        f"**Type:** {memory.entity_type}",
        f"**Owner:** {memory.owner}",
        f"**Created:** {memory.created_at}",
        "",
        "## Content",
        "",
        memory.content,
        "",
        "## Metadata",
        "",
        f"- ID: `{memory.id}`",
        f"- Version: {memory.version}",
        f"- Status: {memory.status}",
        f"- Tags: {', '.join(memory.tags)}",
    ]
    return "\n".join(lines)


def _memory_to_frontmatter(memory: MemoryOut) -> dict[str, Any]:
    """Generate YAML frontmatter from memory metadata."""
    return {
        "title": memory.title,
        "openbrain_id": memory.id,
        "domain": memory.domain,
        "entity_type": memory.entity_type,
        "owner": memory.owner,
        "version": memory.version,
        "status": memory.status,
        "created_at": memory.created_at.isoformat() if hasattr(memory.created_at, 'isoformat') else str(memory.created_at),
        "updated_at": memory.updated_at.isoformat() if hasattr(memory.updated_at, 'isoformat') else str(memory.updated_at),
        "tags": memory.tags,
        "source": "openbrain-export",
    }


def _build_collection_index(
    collection_name: str,
    query: str,
    exported: list[ObsidianExportItem],
    memories: list[MemoryOut],
    group_by: str | None,
) -> str:
    """Build markdown index for collection."""
    lines = [
        f"# {collection_name}",
        "",
        f"*Collection generated from OpenBrain — {len(exported)} items*",
        "",
        f"**Query:** `{query}`",
        "",
    ]

    if group_by and memories:
        lines.append(f"## Grouped by: {group_by}")
        lines.append("")
        
        # Group memories
        groups: dict[str, list[tuple[ObsidianExportItem, MemoryOut]]] = {}
        for exp in exported:
            mem = next((m for m in memories if m.id == exp.memory_id), None)
            if mem:
                if group_by == "entity_type":
                    key = mem.entity_type
                elif group_by == "owner":
                    key = mem.owner or "No owner"
                elif group_by == "tags":
                    key = mem.tags[0] if mem.tags else "Untagged"
                else:
                    key = "Other"
                groups.setdefault(key, []).append((exp, mem))
        
        # Output groups
        for key, items in sorted(groups.items()):
            lines.append(f"### {key}")
            lines.append("")
            for exp, mem in items:
                link_path = exp.path.replace('.md', '')
                lines.append(f"- [[{link_path}]] — {exp.title}")
            lines.append("")
    else:
        lines.append("## Items")
        lines.append("")
        for exp in exported:
            link_path = exp.path.replace('.md', '')
            lines.append(f"- [[{link_path}]] — {exp.title}")
        lines.append("")
    
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Well-Known Discovery (for ChatGPT MCP)
# ---------------------------------------------------------------------------

async def oauth_protected_resource() -> dict:
    """RFC 9470 — tells ChatGPT where to find the OAuth server."""
    return {
        "resource": _public_base or "http://localhost:7010",
        "authorization_servers": [
            os.environ.get("OIDC_ISSUER_URL", "").rstrip("/")
        ],
    }

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

async def healthz() -> dict:
    return {"status": "ok", "service": "openbrain-unified"}


async def readyz() -> dict:
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


async def health(
    _user: dict = Depends(require_auth),
) -> dict:
    return await readyz()


async def diagnostics_metrics(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> dict[str, Any]:
    status_counts = await get_memory_status_counts(session)
    domain_status_counts = await get_memory_domain_status_counts(session)
    set_gauge_metric("active_memories_total", status_counts["active"])
    set_gauge_metric("superseded_memories_total", status_counts["superseded"])
    set_gauge_metric("archived_memories_total", status_counts["archived"])
    set_gauge_metric("deleted_memories_total", status_counts["deleted"])
    for domain, counts in domain_status_counts.items():
        set_gauge_metric(f"active_memories_{domain}_total", counts["active"])
        set_gauge_metric(f"superseded_memories_{domain}_total", counts["superseded"])
    _refresh_operational_gauges()
    snapshot = get_metrics_snapshot()
    snapshot["summary"] = _build_operational_summary()
    return snapshot


async def prometheus_metrics(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> str:
    status_counts = await get_memory_status_counts(session)
    domain_status_counts = await get_memory_domain_status_counts(session)
    set_gauge_metric("active_memories_total", status_counts["active"])
    set_gauge_metric("superseded_memories_total", status_counts["superseded"])
    set_gauge_metric("archived_memories_total", status_counts["archived"])
    set_gauge_metric("deleted_memories_total", status_counts["deleted"])
    for domain, counts in domain_status_counts.items():
        set_gauge_metric(f"active_memories_{domain}_total", counts["active"])
        set_gauge_metric(f"superseded_memories_{domain}_total", counts["superseded"])
    _refresh_operational_gauges()
    return render_prometheus_metrics()

# ---------------------------------------------------------------------------
# API Routes (CRUD)
# ---------------------------------------------------------------------------

async def create_memory(
    data: MemoryCreate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryOut:
    _enforce_domain_access(_user, data.domain, "write")
    data.owner = _resolve_owner_for_write(_user, data.owner)
    data.tenant_id = _resolve_tenant_for_write(_user, data.tenant_id)
    try:
        memory = await store_memory(session, data, actor=_user.get("sub", "agent"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    incr_metric("memories_created_total")
    return memory

async def create_memories_bulk(
    data: list[MemoryCreate],
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> list[MemoryOut]:
    if not data:
        raise HTTPException(status_code=422, detail="Empty list")
    for item in data:
        _enforce_domain_access(_user, item.domain, "write")
        item.owner = _resolve_owner_for_write(_user, item.owner)
        item.tenant_id = _resolve_tenant_for_write(_user, item.tenant_id)
    memories = await store_memories_bulk(session, data)
    incr_metric("bulk_batches_total")
    incr_metric("bulk_records_total", len(data))
    incr_metric("memories_created_total", len(memories))
    return memories

async def bulk_upsert_memories(
    data: list[MemoryUpsertItem],
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> BulkUpsertResult:
    for item in data:
        _enforce_domain_access(_user, item.domain, "write")
        item.owner = _resolve_owner_for_write(_user, item.owner)
        item.tenant_id = _resolve_tenant_for_write(_user, item.tenant_id)
    try:
        result = await upsert_memories_bulk(session, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    incr_metric("bulk_batches_total")
    incr_metric("bulk_records_total", len(data))
    incr_metric("memories_created_total", len(result.inserted))
    incr_metric("memories_updated_total", len(result.updated))
    incr_metric("memories_skipped_total", len(result.skipped))
    return result

async def read_memory(
    memory_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryOut:
    memory = await get_memory(session, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    _enforce_domain_access(_user, memory.domain, "read")
    _enforce_memory_access(_user, memory)
    return memory

async def read_memories(
    domain: str | None = Query(None),
    entity_type: str | None = Query(None),
    status: str | None = Query(None),
    sensitivity: str | None = Query(None),
    owner: str | None = Query(None),
    tenant_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> list[MemoryOut]:
    filters: dict[str, Any] = {}
    if domain:
        filters["domain"] = domain
    if entity_type:
        filters["entity_type"] = entity_type
    if status:
        filters["status"] = status
    if sensitivity:
        filters["sensitivity"] = sensitivity
    if owner:
        filters["owner"] = owner
    if tenant_id:
        filters["tenant_id"] = tenant_id
    return await list_memories(session, _apply_owner_scope(_user, filters), limit)

async def search(
    req: SearchRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> list[SearchResult]:
    req.filters = _apply_owner_scope(_user, req.filters)
    rows = await search_memories(session, req)
    incr_metric("search_requests_total")
    if not rows:
        incr_metric("search_zero_hit_total")
    return [SearchResult(memory=mem, score=score) for mem, score in rows]

async def update(
    memory_id: str,
    data: MemoryUpdate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryOut:
    existing = await get_memory(session, memory_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    _enforce_domain_access(_user, existing.domain, "write")
    _enforce_memory_access(_user, existing)
    data.owner = _resolve_owner_for_write(_user, data.owner if data.owner is not None else existing.owner)
    data.tenant_id = _resolve_tenant_for_write(_user, data.tenant_id if data.tenant_id is not None else existing.tenant_id)
    try:
        memory = await update_memory(session, memory_id, data, actor=_user.get("sub", "agent"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    # Only increment metrics on actual mutation; skipped writes return identical record.
    if memory.id != existing.id:
        incr_metric("memories_versioned_total")
    elif memory.content_hash != existing.content_hash or memory.updated_at != existing.updated_at:
        incr_metric("memories_updated_total")
    return memory

async def delete(
    memory_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> None:
    _require_admin(_user)
    memory = await get_memory(session, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    _enforce_domain_access(_user, memory.domain, "admin")
    try:
        deleted = await delete_memory(session, memory_id, actor=_user.get("sub", "agent"))
    except ValueError as e:
        if "append-only" in str(e).lower():
            incr_metric("policy_skip_total")
            incr_metric("policy_skip_delete_total")
        raise HTTPException(status_code=403, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    incr_metric("memories_deleted_total")

async def check_sync_endpoint(
    req: SyncCheckRequest | None = Body(default=None),
    memory_id: str | None = Query(None),
    match_key: str | None = Query(None),
    obsidian_ref: str | None = Query(None),
    file_hash: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> SyncCheckResponse:
    try:
        resolved_req = req or SyncCheckRequest(
            memory_id=memory_id,
            match_key=match_key,
            obsidian_ref=obsidian_ref,
            file_hash=file_hash,
        )
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        raise HTTPException(status_code=422, detail=first.get("msg", str(exc))) from exc

    result = await sync_check(
        session,
        memory_id=resolved_req.memory_id,
        match_key=resolved_req.match_key,
        obsidian_ref=resolved_req.obsidian_ref,
        file_hash=resolved_req.file_hash,
    )
    if result["status"] != "missing" and result["memory_id"]:
        memory = await get_memory(session, str(result["memory_id"]))
        if memory is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        try:
            _enforce_domain_access(_user, memory.domain, "read")
            _enforce_memory_access(_user, memory)
        except HTTPException as exc:
            raise _hide_memory_access_denied(exc) from exc
    incr_metric("sync_checks_total")
    incr_metric(f"sync_{result['status']}_total")
    return SyncCheckResponse(**result)

async def maintain(
    req: MaintenanceRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MaintenanceReport:
    _require_admin(_user)
    report = await run_maintenance(session, req, actor=_user.get("sub", "agent"))
    policy_skip_count = sum(1 for action in report.actions if action.action == "policy_skip")
    dedup_override_count = sum(1 for action in report.actions if action.action == "dedup_override")
    policy_skip_reasons = _count_policy_skips_by_reason(report.actions)
    incr_metric("maintain_runs_total")
    incr_metric("duplicate_candidates_total", report.dedup_found)
    incr_metric("owner_normalizations_total", report.owners_normalized)
    incr_metric("orphaned_supersession_links_total", report.links_fixed)
    incr_metric("policy_skip_total", policy_skip_count)
    incr_metric("policy_skip_dedup_total", policy_skip_reasons["dedup"])
    incr_metric("policy_skip_owner_normalization_total", policy_skip_reasons["owner_normalization"])
    incr_metric("policy_skip_link_repair_total", policy_skip_reasons["link_repair"])
    incr_metric("dedup_override_total", dedup_override_count)
    return report


async def read_policy_registry(
    _user: dict = Depends(require_auth),
) -> PolicyRegistry:
    _require_admin(_user)
    return PolicyRegistry(**get_policy_registry())


async def update_policy_registry(
    registry: PolicyRegistry,
    _user: dict = Depends(require_auth),
) -> PolicyRegistry:
    _require_admin(_user)
    return PolicyRegistry(**await set_policy_registry(registry.model_dump()))


async def maintain_reports(
    limit: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> list[MaintenanceReportEntry]:
    _require_admin(_user)
    return await list_maintenance_reports(session, limit=limit)


async def maintain_report_detail(
    report_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MaintenanceReportDetail:
    _require_admin(_user)
    report = await get_maintenance_report(session, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Maintenance report not found")
    return report

async def export(
    req: ExportRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> Any:
    _require_admin(_user)
    for memory_id in req.ids:
        memory = await get_memory(session, memory_id)
        if memory is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        try:
            _enforce_domain_access(_user, memory.domain, "read")
            _enforce_memory_access(_user, memory)
        except HTTPException as exc:
            raise _hide_memory_access_denied(exc) from exc
    incr_metric("exports_total")
    # All callers that reach this point have passed _require_admin().
    # Both human admins and the internal service account get unredacted export access.
    records = await export_memories(session, req.ids, role="admin")
    if req.format == "jsonl":
        content = "\n".join(json.dumps(r, default=str) for r in records) + "\n"
        return Response(content=content, media_type="application/x-ndjson")
    return records


# ---------------------------------------------------------------------------
# Bidirectional Sync Handlers (OpenBrain ↔ Obsidian)
# ---------------------------------------------------------------------------

# Global sync tracker instance
_sync_tracker: ObsidianChangeTracker | None = None
_sync_engine: BidirectionalSyncEngine | None = None


def _get_sync_tracker() -> ObsidianChangeTracker:
    """Get or create sync tracker singleton."""
    global _sync_tracker
    if _sync_tracker is None:
        _sync_tracker = ObsidianChangeTracker()
    return _sync_tracker


def _get_sync_engine(strategy: str = "domain_based") -> BidirectionalSyncEngine:
    """Get or create sync engine singleton."""
    global _sync_engine
    if _sync_engine is None:
        strategy_enum = SyncStrategy(strategy)
        _sync_engine = BidirectionalSyncEngine(
            strategy=strategy_enum,
            tracker=_get_sync_tracker(),
        )
    return _sync_engine


async def v1_obsidian_bidirectional_sync(
    req: ObsidianBidirectionalSyncRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> ObsidianBidirectionalSyncResponse:
    """
    Perform bidirectional synchronization between OpenBrain and Obsidian.
    
    Detects and resolves changes in both systems.
    """
    _require_admin(_user)
    
    engine = _get_sync_engine(req.strategy)
    adapter = ObsidianCliAdapter()
    
    result = await engine.sync(
        session=session,
        adapter=adapter,
        vault=req.vault,
        dry_run=req.dry_run,
    )
    
    # Convert to response format
    changes_response = [
        ObsidianSyncChange(
            memory_id=change.memory_id,
            obsidian_path=change.obsidian_path,
            change_type=change.change_type.value,
            source=change.source,
            conflict=change.conflict,
            resolution=change.resolution,
        )
        for change in result.details
    ]
    
    return ObsidianBidirectionalSyncResponse(
        started_at=result.started_at,
        completed_at=result.completed_at,
        vault=req.vault,
        strategy=req.strategy,
        changes_detected=result.changes_detected,
        changes_applied=result.changes_applied,
        conflicts=result.conflicts,
        dry_run=req.dry_run,
        errors=result.errors,
        changes=changes_response,
    )


async def v1_obsidian_sync_status(
    _user: dict = Depends(require_auth),
) -> ObsidianSyncStatus:
    """Get status of sync tracking."""
    _require_admin(_user)
    
    tracker = _get_sync_tracker()
    stats = tracker.get_stats()
    
    return ObsidianSyncStatus(**stats).model_dump()


async def v1_obsidian_update_note(
    vault: str,
    path: str,
    content: str | None = None,
    append: bool = False,
    tags: list[str] | None = None,
    _user: dict = Depends(require_auth),
) -> ObsidianWriteResponse:
    """Update an existing note in Obsidian."""
    _require_admin(_user)
    
    adapter = ObsidianCliAdapter()
    
    # Build frontmatter update if tags provided
    frontmatter = None
    if tags:
        frontmatter = {"tags": tags}
    
    try:
        note = await adapter.update_note(
            vault=vault,
            path=path,
            content=content,
            frontmatter=frontmatter,
            append=append,
        )
    except ObsidianCliError as e:
        raise HTTPException(status_code=503, detail=str(e))
    
    return ObsidianWriteResponse(
        vault=note.vault,
        path=note.path,
        title=note.title,
        content=note.content,
        frontmatter=note.frontmatter,
        tags=note.tags,
        file_hash=note.file_hash,
        created=False,  # It was an update
    )


# ---------------------------------------------------------------------------
# Route Registration
# ---------------------------------------------------------------------------

register_v1_routes(app, handlers=__import__(__name__, fromlist=["*"]))
register_ops_routes(app, handlers=__import__(__name__, fromlist=["*"]))
register_crud_routes(app, handlers=__import__(__name__, fromlist=["*"]))
