"""
OpenBrain Unified v2.0 — FastAPI Memory Service.

REST API for the unified memory store.
Runs in Docker on port 80 (mapped to 7010 externally).
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

import structlog
from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import (
    PUBLIC_MODE,
    get_domain_scope,
    get_policy_registry,
    get_registry_domain_scope,
    get_subject,
    get_tenant_id,
    is_privileged_user,
    require_auth,
    set_policy_registry,
)
from .crud import (
    delete_memory,
    export_memories,
    find_memories_v1,
    get_grounding_pack,
    get_memory,
    get_memory_as_record,
    get_memory_domain_status_counts,
    get_memory_status_counts,
    get_maintenance_report,
    handle_memory_write,
    handle_memory_write_many,
    list_memories,
    list_maintenance_reports,
    run_maintenance,
    search_memories,
    store_memories_bulk,
    store_memory,
    sync_check,
    update_memory,
    upsert_memories_bulk,
)
from .db import AsyncSessionLocal, get_session
from .obsidian_cli import ObsidianCliAdapter, ObsidianCliError, note_to_memory_write_record
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
    ObsidianNoteResponse,
    ObsidianReadRequest,
    ObsidianSyncRequest,
    ObsidianSyncResponse,
    PolicyRegistry,
    SearchRequest,
    SearchResult,
    SyncCheckRequest,
    SyncCheckResponse,
)
from .telemetry import get_metrics_snapshot, incr_metric, render_prometheus_metrics, set_gauge_metric
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


def _require_admin(user: dict[str, Any]) -> None:
    if not PUBLIC_MODE:
        return
    if not is_privileged_user(user):
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
        raise HTTPException(status_code=403, detail=f"{action.capitalize()} access denied for domain '{domain}'")
    # Fail-closed: deny unless there is an explicit non-empty grant that includes
    # this domain. An empty allowed set means no grants were configured for this
    # user+action pair, not "all domains permitted" (C1 fix).
    if domain.lower() not in allowed:
        raise HTTPException(status_code=403, detail=f"{action.capitalize()} access denied for domain '{domain}'")


def _resolve_owner_for_write(user: dict[str, Any], owner: str | None) -> str:
    if not _is_scoped_user(user):
        return owner or ""
    if get_tenant_id(user):
        return owner or ""
    subject = get_subject(user)
    if owner and owner != subject:
        raise HTTPException(status_code=403, detail="Cannot write records for another owner")
    return subject


def _resolve_tenant_for_write(user: dict[str, Any], tenant_id: str | None) -> str | None:
    if not _is_scoped_user(user):
        return tenant_id
    scoped_tenant = get_tenant_id(user)
    if not scoped_tenant:
        return tenant_id
    if tenant_id and tenant_id != scoped_tenant:
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
            raise HTTPException(status_code=404, detail="Memory not found")
        return
    subject = get_subject(user)
    if not memory.owner or memory.owner != subject:
        raise HTTPException(status_code=404, detail="Memory not found")

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
    _enforce_domain_access(_user, req.record.domain, "write")
    req.record.owner = _resolve_owner_for_write(_user, req.record.owner)
    req.record.tenant_id = _resolve_tenant_for_write(_user, req.record.tenant_id)
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

@app.post("/api/v1/memory/write-many", response_model=MemoryWriteManyResponse)
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

@app.post("/api/v1/memory/find", response_model=list[dict[str, Any]])
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

@app.post("/api/v1/memory/get-context", response_model=MemoryGetContextResponse)
async def v1_get_context(
    req: MemoryGetContextRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MemoryGetContextResponse:
    if req.domain:
        _enforce_domain_access(_user, req.domain, "read")
    owner = get_subject(_user) if _is_scoped_user(_user) and not get_tenant_id(_user) else None
    tenant_id = get_tenant_id(_user) if _is_scoped_user(_user) else None
    response = await get_grounding_pack(session, req, owner=owner, tenant_id=tenant_id)
    incr_metric("get_context_requests_total")
    return response


@app.get("/api/v1/memory/{memory_id}", response_model=MemoryRecord)
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


@app.get("/api/v1/obsidian/vaults", response_model=list[str])
async def v1_obsidian_vaults(
    _user: dict = Depends(require_auth),
) -> list[str]:
    _require_admin(_user)
    adapter = ObsidianCliAdapter()
    try:
        return await adapter.list_vaults()
    except ObsidianCliError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/api/v1/obsidian/read-note", response_model=ObsidianNoteResponse)
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


@app.post("/api/v1/obsidian/sync", response_model=ObsidianSyncResponse)
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

@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "service": "openbrain-unified"}


@app.get("/readyz")
async def readyz() -> dict:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok", "service": "openbrain-unified", "db": "ok"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "service": "openbrain-unified", "db": "error"},
        )


@app.get("/health")
async def health(
    _user: dict = Depends(require_auth),
) -> dict:
    return await readyz()


@app.get("/api/diagnostics/metrics")
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


@app.get("/metrics", response_class=PlainTextResponse)
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

@app.post("/api/memories", response_model=MemoryOut, status_code=201)
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

@app.post("/api/memories/bulk", response_model=list[MemoryOut], status_code=201)
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

@app.post("/api/memories/bulk-upsert", response_model=BulkUpsertResult, status_code=200)
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

@app.get("/api/memories/{memory_id}", response_model=MemoryOut)
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

@app.get("/api/memories", response_model=list[MemoryOut])
async def read_memories(
    domain: str | None = Query(None),
    tenant_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> list[MemoryOut]:
    filters: dict[str, Any] = {}
    if domain:
        filters["domain"] = domain
    if tenant_id:
        filters["tenant_id"] = tenant_id
    return await list_memories(session, _apply_owner_scope(_user, filters), limit)

@app.post("/api/memories/search", response_model=list[SearchResult])
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

@app.put("/api/memories/{memory_id}", response_model=MemoryOut)
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
    memory = await update_memory(session, memory_id, data, actor=_user.get("sub", "agent"))
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    if memory.version > 1:
        incr_metric("memories_versioned_total")
    else:
        incr_metric("memories_updated_total")
    return memory

@app.delete("/api/memories/{memory_id}", status_code=204)
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

@app.post("/api/memories/sync-check", response_model=SyncCheckResponse)
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
    incr_metric("sync_checks_total")
    incr_metric(f"sync_{result['status']}_total")
    return SyncCheckResponse(**result)

@app.post("/api/admin/maintain", response_model=MaintenanceReport)
async def maintain(
    req: MaintenanceRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> MaintenanceReport:
    _require_admin(_user)
    report = await run_maintenance(session, req, actor=_user.get("sub", "agent"))
    policy_skip_count = sum(1 for action in report.actions if action.action == "policy_skip")
    policy_skip_reasons = _count_policy_skips_by_reason(report.actions)
    incr_metric("maintain_runs_total")
    incr_metric("duplicate_candidates_total", report.dedup_found)
    incr_metric("owner_normalizations_total", report.owners_normalized)
    incr_metric("orphaned_supersession_links_total", report.links_fixed)
    incr_metric("policy_skip_total", policy_skip_count)
    incr_metric("policy_skip_dedup_total", policy_skip_reasons["dedup"])
    incr_metric("policy_skip_owner_normalization_total", policy_skip_reasons["owner_normalization"])
    incr_metric("policy_skip_link_repair_total", policy_skip_reasons["link_repair"])
    return report


@app.get("/api/admin/policy-registry", response_model=PolicyRegistry)
async def read_policy_registry(
    _user: dict = Depends(require_auth),
) -> PolicyRegistry:
    _require_admin(_user)
    return PolicyRegistry(**get_policy_registry())


@app.put("/api/admin/policy-registry", response_model=PolicyRegistry)
async def update_policy_registry(
    registry: PolicyRegistry,
    _user: dict = Depends(require_auth),
) -> PolicyRegistry:
    _require_admin(_user)
    return PolicyRegistry(**set_policy_registry(registry.model_dump()))


@app.get("/api/admin/maintain/reports", response_model=list[MaintenanceReportEntry])
async def maintain_reports(
    limit: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> list[MaintenanceReportEntry]:
    _require_admin(_user)
    return await list_maintenance_reports(session, limit=limit)


@app.get("/api/admin/maintain/reports/{report_id}", response_model=MaintenanceReportDetail)
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

@app.post("/api/memories/export")
async def export(
    req: ExportRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> Any:
    _require_admin(_user)
    incr_metric("exports_total")
    # All callers that reach this point have passed _require_admin().
    # Both human admins and the internal service account get unredacted export access.
    records = await export_memories(session, req.ids, role="admin")
    if req.format == "jsonl":
        content = "\n".join(json.dumps(r, default=str) for r in records) + "\n"
        return Response(content=content, media_type="application/x-ndjson")
    return records
