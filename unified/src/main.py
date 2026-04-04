"""
OpenBrain Unified v2.0 — FastAPI Memory Service.

REST API for the unified memory store.
Runs in Docker on port 80 (mapped to 7010 externally).
"""

from __future__ import annotations

import json
import os
from typing import Any

import structlog
from fastapi import Body, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from .app_factory import create_app
from .auth import (
    PUBLIC_EXPOSURE,
    get_policy_registry,
    require_auth,
    set_policy_registry,
)
from .db import get_session
from .lifespan import lifespan
from .middleware import MetricsMiddleware, RequestIDMiddleware
from .memory_reads import (
    export_memories,
    get_memory,
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
    run_maintenance,
    store_memories_bulk,
    store_memory,
    update_memory,
    upsert_memories_bulk,
)
from .routes_crud import register_crud_routes
from .api.v1 import health_router, memory_router, obsidian_router
from .routes_ops import register_ops_routes
from .schemas import (
    BulkUpsertResult,
    ExportRequest,
    MaintenanceReport,
    MaintenanceReportDetail,
    MaintenanceReportEntry,
    MaintenanceRequest,
    MemoryCreate,
    MemoryOut,
    MemoryUpdate,
    MemoryUpsertItem,
    PolicyRegistry,
    SearchRequest,
    SearchResult,
    SyncCheckRequest,
    SyncCheckResponse,
)
from .security import (
    require_admin as _require_admin,
    enforce_domain_access as _enforce_domain_access,
    resolve_owner_for_write as _resolve_owner_for_write,
    resolve_tenant_for_write as _resolve_tenant_for_write,
    apply_owner_scope as _apply_owner_scope,
    enforce_memory_access as _enforce_memory_access,
    hide_memory_access_denied as _hide_memory_access_denied,
    _effective_domain_scope,
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
        summary["policy_skip_per_maintain_run_ratio"]
        >= ALERT_THRESHOLDS["policy_skip_per_maintain_run_ratio"]["elevated"]
        or summary["duplicate_candidates_per_maintain_run_ratio"]
        >= ALERT_THRESHOLDS["duplicate_candidates_per_maintain_run_ratio"]["elevated"]
        or summary["search_zero_hit_ratio"]
        >= ALERT_THRESHOLDS["search_zero_hit_ratio"]["elevated"]
    ):
        return 2
    if (
        summary["policy_skip_per_maintain_run_ratio"]
        >= ALERT_THRESHOLDS["policy_skip_per_maintain_run_ratio"]["watch"]
        or summary["duplicate_candidates_per_maintain_run_ratio"]
        >= ALERT_THRESHOLDS["duplicate_candidates_per_maintain_run_ratio"]["watch"]
        or summary["search_zero_hit_ratio"]
        >= ALERT_THRESHOLDS["search_zero_hit_ratio"]["watch"]
    ):
        return 1
    return 0


def _build_operational_summary() -> dict[
    str, float | str | dict[str, dict[str, float]]
]:
    counters = get_metrics_snapshot()["counters"]
    maintain_runs = int(counters.get("maintain_runs_total", 0))
    policy_skips = int(counters.get("policy_skip_total", 0))
    duplicate_candidates = int(counters.get("duplicate_candidates_total", 0))
    summary: dict[str, float | str | dict[str, dict[str, float]]] = {
        "policy_skip_per_maintain_run_ratio": _safe_ratio(policy_skips, maintain_runs),
        "duplicate_candidates_per_maintain_run_ratio": _safe_ratio(
            duplicate_candidates, maintain_runs
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
    health_status = _compute_operational_health(
        {
            "policy_skip_per_maintain_run_ratio": float(
                summary["policy_skip_per_maintain_run_ratio"]
            ),
            "duplicate_candidates_per_maintain_run_ratio": float(
                summary["duplicate_candidates_per_maintain_run_ratio"]
            ),
            "versioned_to_updated_ratio": float(summary["versioned_to_updated_ratio"]),
            "search_zero_hit_ratio": float(summary["search_zero_hit_ratio"]),
        }
    )
    if health_status == 2:
        health = "elevated"
    elif health_status == 1:
        health = "watch"
    else:
        health = "normal"
    return {
        "health": health,
        "health_status": float(health_status),
        "thresholds": ALERT_THRESHOLDS,
        **summary,
    }


app.add_middleware(MetricsMiddleware)
app.add_middleware(RequestIDMiddleware)

# ---------------------------------------------------------------------------
# New Modular V1 Routers (Refactored)
# ---------------------------------------------------------------------------

app.include_router(health_router)
app.include_router(memory_router, prefix="/api/v1")
app.include_router(obsidian_router, prefix="/api/v1")

# ---------------------------------------------------------------------------
# Well-Known Discovery (for ChatGPT MCP)
# ---------------------------------------------------------------------------


async def oauth_protected_resource() -> dict:
    """RFC 9470 — tells ChatGPT where to find the OAuth server."""
    return {
        "resource": _public_base or "http://localhost:7010",
        "authorization_servers": [os.environ.get("OIDC_ISSUER_URL", "").rstrip("/")],
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


# Register well-known routes
app.add_api_route(
    "/.well-known/oauth-protected-resource", oauth_protected_resource, methods=["GET"]
)
app.add_api_route(
    "/.well-known/oauth-authorization-server",
    oauth_authorization_server,
    methods=["GET"],
)

# ---------------------------------------------------------------------------
# Health & Diagnostics
# ---------------------------------------------------------------------------


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
    data.owner = _resolve_owner_for_write(
        _user, data.owner if data.owner is not None else existing.owner
    )
    data.tenant_id = _resolve_tenant_for_write(
        _user, data.tenant_id if data.tenant_id is not None else existing.tenant_id
    )
    try:
        memory = await update_memory(
            session, memory_id, data, actor=_user.get("sub", "agent")
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    # Only increment metrics on actual mutation; skipped writes return identical record.
    if memory.id != existing.id:
        incr_metric("memories_versioned_total")
    elif (
        memory.content_hash != existing.content_hash
        or memory.updated_at != existing.updated_at
    ):
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
        deleted = await delete_memory(
            session, memory_id, actor=_user.get("sub", "agent")
        )
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
    policy_skip_count = sum(
        1 for action in report.actions if action.action == "policy_skip"
    )
    dedup_override_count = sum(
        1 for action in report.actions if action.action == "dedup_override"
    )
    policy_skip_reasons = _count_policy_skips_by_reason(report.actions)
    incr_metric("maintain_runs_total")
    incr_metric("duplicate_candidates_total", report.dedup_found)
    incr_metric("owner_normalizations_total", report.owners_normalized)
    incr_metric("orphaned_supersession_links_total", report.links_fixed)
    incr_metric("policy_skip_total", policy_skip_count)
    incr_metric("policy_skip_dedup_total", policy_skip_reasons["dedup"])
    incr_metric(
        "policy_skip_owner_normalization_total",
        policy_skip_reasons["owner_normalization"],
    )
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
# Route Registration
# ---------------------------------------------------------------------------

register_ops_routes(app, handlers=__import__(__name__, fromlist=["*"]))
register_crud_routes(app, handlers=__import__(__name__, fromlist=["*"]))
