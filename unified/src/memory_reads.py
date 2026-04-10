from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .crud_common import (
    STATUS_DUPLICATE,
    STATUS_SUPERSEDED,
    _export_record,
    _tenant_filter_expr,
    _to_out,
    _to_record,
)
from .embed import get_embedding
from .models import AuditLog, DomainEnum, Memory
from .repositories import MemoryRepository, SQLAlchemyMemoryRepository
from .schemas import (
    MaintenanceAction,
    MaintenanceReportDetail,
    MaintenanceReportEntry,
    MemoryFindRequest,
    MemoryGetContextRequest,
    MemoryGetContextResponse,
    MemoryOut,
    MemoryRecord,
    SearchRequest,
    TestDataActionSuggestion,
    TestDataHygieneReport,
    TestDataSampleEntry,
)


async def _get_embedding_compat(text: str):
    """Get embedding using direct reference."""
    return await get_embedding(text)


async def get_memory_raw(session: AsyncSession, memory_id: str) -> Memory:
    """
    Get raw Memory model by ID (internal use).

    Args:
        session: Database session
        memory_id: Memory ID

    Returns:
        Memory model instance
    """
    stmt = select(Memory).where(Memory.id == memory_id)
    res = await session.execute(stmt)
    return res.scalar_one()


async def get_memory(session: AsyncSession, memory_id: str) -> MemoryOut | None:
    """
    Get memory by ID and convert to output schema.

    Args:
        session: Database session
        memory_id: Memory ID

    Returns:
        Memory output or None if not found
    """
    stmt = select(Memory).where(Memory.id == memory_id)
    result = await session.execute(stmt)
    memory = result.scalar_one_or_none()
    return _to_out(memory) if memory else None


async def get_memory_as_record(
    session: AsyncSession, memory_id: str
) -> tuple[MemoryRecord | None, MemoryOut | None]:
    """
    Get memory as both record and output formats.

    Args:
        session: Database session
        memory_id: Memory ID

    Returns:
        Tuple of (MemoryRecord, MemoryOut) or (None, None) if not found
    """
    stmt = select(Memory).where(Memory.id == memory_id)
    result = await session.execute(stmt)
    memory = result.scalar_one_or_none()
    if memory is None:
        return None, None
    return _to_record(memory), _to_out(memory)


# ============================================================================
# Repository-based API (New - ARCH-002)
# ============================================================================


def get_repository(session: AsyncSession) -> MemoryRepository:
    """Factory function to get the appropriate repository instance."""
    return SQLAlchemyMemoryRepository(session)


async def get_memory_with_repo(
    session: AsyncSession, memory_id: str
) -> MemoryOut | None:
    """Get memory using repository pattern."""
    repo = get_repository(session)
    memory = await repo.get_by_id(memory_id)
    return _to_out(memory) if memory else None


def _apply_filters_to_stmt(
    stmt,
    filters: dict[str, Any],
    *,
    default_status_filter: bool = True,
) -> Any:
    """
    Apply common filters to a SQLAlchemy select statement.

    Args:
        stmt: The SQLAlchemy select statement to filter
        filters: Dictionary of filter conditions
        default_status_filter: If True, exclude superseded/duplicate by default

    Returns:
        Modified statement with filters applied
    """
    raw_include_test_data = filters.get("include_test_data", False)
    if not isinstance(raw_include_test_data, bool):
        raise ValueError(
            "filters.include_test_data must be bool when provided "
            f"(got {type(raw_include_test_data).__name__})"
        )
    include_test_data = raw_include_test_data
    if not include_test_data:
        # Hide explicitly flagged test fixtures from default operational retrieval.
        stmt = stmt.where(
            func.coalesce(Memory.metadata_["test_data"].astext, "false") != "true"
        )

    if "domain" in filters:
        domains = (
            filters["domain"]
            if isinstance(filters["domain"], list)
            else [filters["domain"]]
        )
        stmt = stmt.where(Memory.domain.in_([DomainEnum(domain) for domain in domains]))
    if "entity_type" in filters:
        entity_types = filters["entity_type"]
        if isinstance(entity_types, list):
            stmt = stmt.where(Memory.entity_type.in_(entity_types))
        else:
            stmt = stmt.where(Memory.entity_type == entity_types)
    if "status" in filters:
        stmt = stmt.where(Memory.status == filters["status"])
    elif default_status_filter:
        stmt = stmt.where(Memory.status.notin_([STATUS_SUPERSEDED, STATUS_DUPLICATE]))
    if "sensitivity" in filters:
        stmt = stmt.where(Memory.sensitivity == filters["sensitivity"])
    if "owner" in filters:
        owners = filters["owner"]
        if isinstance(owners, list):
            stmt = stmt.where(Memory.owner.in_(owners))
        else:
            stmt = stmt.where(Memory.owner == owners)
    if "tenant_id" in filters:
        tenant_ids = filters["tenant_id"]
        if isinstance(tenant_ids, list):
            stmt = stmt.where(_tenant_filter_expr(tenant_ids))
        else:
            stmt = stmt.where(_tenant_filter_expr([tenant_ids]))
    if "tags_any" in filters:
        stmt = stmt.where(Memory.tags.overlap(filters["tags_any"]))

    return stmt


async def list_memories(
    session: AsyncSession, filters: dict[str, Any], limit: int = 20
) -> list[MemoryOut]:
    """List memories with filtering and pagination."""
    stmt = select(Memory)
    stmt = _apply_filters_to_stmt(stmt, filters, default_status_filter=True)
    stmt = stmt.order_by(Memory.updated_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return [_to_out(memory) for memory in result.scalars().all()]


async def search_memories(
    session: AsyncSession, req: SearchRequest
) -> list[tuple[MemoryOut, float]]:
    """Semantic search memories with vector similarity."""
    embedding = await _get_embedding_compat(req.query)
    stmt = select(
        Memory, Memory.embedding.cosine_distance(embedding).label("distance")
    ).where(Memory.status == "active")
    stmt = _apply_filters_to_stmt(stmt, req.filters, default_status_filter=False)
    stmt = stmt.order_by("distance").limit(req.top_k)
    result = await session.execute(stmt)
    return [(_to_out(row.Memory), 1.0 - float(row.distance)) for row in result.all()]


async def export_memories(
    session: AsyncSession, ids: list[str], role: str = "service"
) -> list[dict]:
    """
    Export memories by IDs with sensitivity-based redaction.

    Args:
        session: Database session
        ids: List of memory IDs to export
        role: Role of the exporter (affects redaction level)

    Returns:
        List of exported memory records with redacted sensitive fields
    """
    stmt = select(Memory).where(Memory.id.in_(ids))
    result = await session.execute(stmt)
    memories = result.scalars().all()
    exported = []
    for memory in memories:
        out = _to_out(memory).model_dump(mode="json")
        exported.append(_export_record(out, memory.sensitivity, role))
    return exported


async def sync_check(
    session: AsyncSession,
    *,
    memory_id: str | None = None,
    match_key: str | None = None,
    obsidian_ref: str | None = None,
    file_hash: str | None = None,
) -> dict[str, str | None]:
    """
    Check if a memory exists and if it's up to date based on content hash.

    Args:
        session: Database session
        memory_id: Memory ID to check
        match_key: Match key to check (alternative to memory_id)
        obsidian_ref: Obsidian reference to check (alternative to memory_id)
        file_hash: Content hash to compare (optional)

    Returns:
        Dictionary with status, memory_id, match_key, obsidian_ref,
        stored_hash, provided_hash

    Raises:
        ValueError: If none of memory_id, match_key, obsidian_ref is provided
    """
    if memory_id is None and match_key is None and obsidian_ref is None:
        raise ValueError(
            "Exactly one of memory_id, match_key, or obsidian_ref must be provided."
        )

    stmt = select(Memory).where(Memory.status == "active")
    if memory_id is not None:
        stmt = stmt.where(Memory.id == memory_id)
    elif match_key is not None:
        stmt = (
            stmt.where(Memory.match_key == match_key)
            .order_by(Memory.updated_at.desc())
            .limit(1)
        )
    else:
        stmt = (
            stmt.where(Memory.obsidian_ref == obsidian_ref)
            .order_by(Memory.updated_at.desc())
            .limit(1)
        )

    result = await session.execute(stmt)
    memory = result.scalar_one_or_none()
    if memory is None:
        return {
            "status": "missing",
            "message": "Memory not found.",
            "memory_id": memory_id,
            "match_key": match_key,
            "obsidian_ref": obsidian_ref,
            "stored_hash": None,
            "provided_hash": file_hash,
        }

    response: dict[str, str | None] = {
        "memory_id": memory.id,
        "match_key": memory.match_key,
        "obsidian_ref": memory.obsidian_ref,
        "stored_hash": memory.content_hash,
        "provided_hash": file_hash,
    }
    if file_hash is None:
        response.update({"status": "exists", "message": "Memory exists."})
        return response
    if memory.content_hash != file_hash:
        response.update(
            {"status": "outdated", "message": "Hash mismatch. Update required."}
        )
        return response
    response.update({"status": "synced", "message": "Memory is up to date."})
    return response


async def get_memory_status_counts(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        select(Memory.status, func.count(Memory.id))
        .where(func.coalesce(Memory.metadata_["test_data"].astext, "false") != "true")
        .group_by(Memory.status)
    )
    counts = {status: count for status, count in result.all()}
    return {
        "active": int(counts.get("active", 0)),
        "superseded": int(counts.get("superseded", 0)),
        "archived": int(counts.get("archived", 0)),
        "deleted": int(counts.get("deleted", 0)),
    }


async def get_memory_domain_status_counts(
    session: AsyncSession,
) -> dict[str, dict[str, int]]:
    result = await session.execute(
        select(Memory.domain, Memory.status, func.count(Memory.id))
        .where(func.coalesce(Memory.metadata_["test_data"].astext, "false") != "true")
        .group_by(Memory.domain, Memory.status)
    )
    counts: dict[str, dict[str, int]] = {
        "corporate": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
        "build": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
        "personal": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
    }
    for domain, status, count in result.all():
        domain_key = domain.value if isinstance(domain, DomainEnum) else str(domain)
        if domain_key not in counts:
            counts[domain_key] = {
                "active": 0,
                "superseded": 0,
                "archived": 0,
                "deleted": 0,
            }
        counts[domain_key][str(status)] = int(count)
    return counts


async def get_hidden_test_data_counts(session: AsyncSession) -> dict[str, int]:
    """Return counts for records flagged as test data in metadata."""
    is_test_data = (
        func.coalesce(Memory.metadata_["test_data"].astext, "false") == "true"
    )

    total_result = await session.execute(
        select(func.count(Memory.id)).where(is_test_data)
    )
    active_result = await session.execute(
        select(func.count(Memory.id)).where(is_test_data, Memory.status == "active")
    )
    build_active_result = await session.execute(
        select(func.count(Memory.id)).where(
            is_test_data, Memory.status == "active", Memory.domain == DomainEnum.build
        )
    )
    corporate_active_result = await session.execute(
        select(func.count(Memory.id)).where(
            is_test_data,
            Memory.status == "active",
            Memory.domain == DomainEnum.corporate,
        )
    )
    personal_active_result = await session.execute(
        select(func.count(Memory.id)).where(
            is_test_data,
            Memory.status == "active",
            Memory.domain == DomainEnum.personal,
        )
    )

    return {
        "hidden_test_data_total": int(total_result.scalar() or 0),
        "hidden_test_data_active_total": int(active_result.scalar() or 0),
        "hidden_test_data_build_total": int(build_active_result.scalar() or 0),
        "hidden_test_data_corporate_total": int(corporate_active_result.scalar() or 0),
        "hidden_test_data_personal_total": int(personal_active_result.scalar() or 0),
    }


async def get_test_data_hygiene_report(
    session: AsyncSession, sample_limit: int = 20
) -> TestDataHygieneReport:
    """Return a read-only hygiene report for records flagged as test data."""
    visible_status_counts = await get_memory_status_counts(session)
    visible_domain_status_counts = await get_memory_domain_status_counts(session)
    hidden_counts = await get_hidden_test_data_counts(session)
    is_test_data = (
        func.coalesce(Memory.metadata_["test_data"].astext, "false") == "true"
    )

    status_result = await session.execute(
        select(Memory.status, func.count(Memory.id))
        .where(is_test_data)
        .group_by(Memory.status)
    )
    status_counts = {
        str(status): int(count)
        for status, count in status_result.all()
    }

    domain_result = await session.execute(
        select(Memory.domain, Memory.status, func.count(Memory.id))
        .where(is_test_data)
        .group_by(Memory.domain, Memory.status)
    )
    domain_status_counts: dict[str, dict[str, int]] = {
        "corporate": {},
        "build": {},
        "personal": {},
    }
    for domain, status, count in domain_result.all():
        domain_key = domain.value if isinstance(domain, DomainEnum) else str(domain)
        domain_status_counts.setdefault(domain_key, {})
        domain_status_counts[domain_key][str(status)] = int(count)

    top_owners_result = await session.execute(
        select(Memory.owner, func.count(Memory.id))
        .where(is_test_data)
        .group_by(Memory.owner)
        .order_by(func.count(Memory.id).desc(), Memory.owner.asc())
        .limit(10)
    )
    top_owners = {
        str(owner or ""): int(count)
        for owner, count in top_owners_result.all()
    }

    match_key_prefix_result = await session.execute(
        select(
            func.split_part(func.coalesce(Memory.match_key, ""), ":", 1),
            func.count(Memory.id),
        )
        .where(is_test_data, Memory.match_key.is_not(None))
        .group_by(func.split_part(func.coalesce(Memory.match_key, ""), ":", 1))
        .order_by(func.count(Memory.id).desc())
        .limit(10)
    )
    match_key_prefix_counts = {
        (str(prefix or "") or "<empty>"): int(count)
        for prefix, count in match_key_prefix_result.all()
    }

    null_match_key_result = await session.execute(
        select(func.count(Memory.id)).where(is_test_data, Memory.match_key.is_(None))
    )
    null_match_key_count = int(null_match_key_result.scalar() or 0)

    recommended_actions: list[TestDataActionSuggestion] = []
    hidden_total = int(hidden_counts.get("hidden_test_data_total", 0))
    hidden_build = int(hidden_counts.get("hidden_test_data_build_total", 0))
    hidden_corporate = int(hidden_counts.get("hidden_test_data_corporate_total", 0))

    if hidden_total == 0:
        recommended_actions.append(
            TestDataActionSuggestion(
                code="no_action_needed",
                priority="low",
                summary="No records flagged as test data were detected.",
            )
        )
    else:
        if hidden_build > 0:
            recommended_actions.append(
                TestDataActionSuggestion(
                    code="cleanup_build_test_data",
                    priority="high",
                    summary=(
                        "Build-domain test data detected; schedule controlled delete flow "
                        "(dry-run list -> approve -> delete)."
                    ),
                )
            )
        if hidden_corporate > 0:
            recommended_actions.append(
                TestDataActionSuggestion(
                    code="review_corporate_test_data",
                    priority="high",
                    summary=(
                        "Corporate-domain test data detected; keep append-only constraints and "
                        "review quarantine-only remediation."
                    ),
                )
            )
        if null_match_key_count > 0:
            recommended_actions.append(
                TestDataActionSuggestion(
                    code="normalize_missing_match_keys",
                    priority="medium",
                    summary=(
                        "Some test-data records have null match_key; add deterministic key policy "
                        "to improve dedup and cleanup safety."
                    ),
                )
            )
        if top_owners:
            recommended_actions.append(
                TestDataActionSuggestion(
                    code="owner_feedback_loop",
                    priority="medium",
                    summary=(
                        "Top owners are identifiable; align ingestion hygiene with owners to reduce "
                        "future test-data churn."
                    ),
                )
            )

    sample_result = await session.execute(
        select(
            Memory.id,
            Memory.domain,
            Memory.status,
            Memory.owner,
            Memory.match_key,
            Memory.created_at,
            Memory.updated_at,
        )
        .where(is_test_data)
        .order_by(Memory.updated_at.desc())
        .limit(sample_limit)
    )
    sample = [
        TestDataSampleEntry(
            id=str(row.id),
            domain=(
                row.domain.value if isinstance(row.domain, DomainEnum) else str(row.domain)
            ),
            status=str(row.status),
            owner=str(row.owner or ""),
            match_key=(str(row.match_key) if row.match_key else None),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in sample_result.all()
    ]

    return TestDataHygieneReport(
        generated_at=datetime.now(timezone.utc),
        sample_limit=sample_limit,
        visible_status_counts=visible_status_counts,
        visible_domain_status_counts=visible_domain_status_counts,
        hidden_counts=hidden_counts,
        status_counts=status_counts,
        domain_status_counts=domain_status_counts,
        top_owners=top_owners,
        match_key_prefix_counts=match_key_prefix_counts,
        null_match_key_count=null_match_key_count,
        recommended_actions=recommended_actions,
        sample=sample,
    )


async def list_maintenance_reports(
    session: AsyncSession, limit: int = 20
) -> list[MaintenanceReportEntry]:
    result = await session.execute(
        select(AuditLog)
        .where(
            AuditLog.operation == "maintain", AuditLog.tool_name == "memory.maintain"
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    reports: list[MaintenanceReportEntry] = []
    for entry in result.scalars().all():
        meta = entry.meta or {}
        actions = meta.get("actions") or []
        reports.append(
            MaintenanceReportEntry(
                report_id=entry.id,
                created_at=entry.created_at,
                actor=entry.actor,
                dry_run=bool(meta.get("dry_run", True)),
                total_scanned=int(meta.get("total_scanned", 0)),
                dedup_found=int(meta.get("dedup_found", 0)),
                owners_normalized=int(meta.get("owners_normalized", 0)),
                links_fixed=int(meta.get("links_fixed", 0)),
                action_count=len(actions),
            )
        )
    return reports


async def get_maintenance_report(
    session: AsyncSession, report_id: str
) -> MaintenanceReportDetail | None:
    result = await session.execute(
        select(AuditLog).where(
            AuditLog.id == report_id,
            AuditLog.operation == "maintain",
            AuditLog.tool_name == "memory.maintain",
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return None

    meta = entry.meta or {}
    actions = [MaintenanceAction(**action) for action in (meta.get("actions") or [])]
    return MaintenanceReportDetail(
        report_id=entry.id,
        created_at=entry.created_at,
        actor=entry.actor,
        dry_run=bool(meta.get("dry_run", True)),
        actions=actions,
        total_scanned=int(meta.get("total_scanned", 0)),
        dedup_found=int(meta.get("dedup_found", 0)),
        owners_normalized=int(meta.get("owners_normalized", 0)),
        links_fixed=int(meta.get("links_fixed", 0)),
    )


async def find_memories_v1(
    session: AsyncSession, req: MemoryFindRequest
) -> list[tuple[MemoryRecord, float]]:
    """Find memories with optional semantic search and filtering."""
    embedding = await _get_embedding_compat(req.query) if req.query else None
    if embedding:
        stmt = select(
            Memory, Memory.embedding.cosine_distance(embedding).label("distance")
        ).where(Memory.status == "active")
    else:
        stmt = select(Memory).where(Memory.status == "active")

    stmt = _apply_filters_to_stmt(stmt, req.filters, default_status_filter=False)

    if embedding and req.sort == "relevance":
        stmt = stmt.order_by("distance")
    else:
        stmt = stmt.order_by(Memory.updated_at.desc())

    stmt = stmt.limit(req.limit)
    result = await session.execute(stmt)
    if embedding:
        return [
            (_to_record(row.Memory), 1.0 - float(row.distance)) for row in result.all()
        ]
    return [(_to_record(memory), 1.0) for memory in result.scalars().all()]


async def get_grounding_pack(
    session: AsyncSession,
    req: MemoryGetContextRequest,
    owner: str | None = None,
    tenant_id: str | None = None,
) -> MemoryGetContextResponse:
    find_req = MemoryFindRequest(
        query=req.query,
        filters={"domain": req.domain} if req.domain else {},
        limit=req.max_items,
    )
    if owner:
        find_req.filters["owner"] = owner
    if tenant_id:
        find_req.filters["tenant_id"] = tenant_id
    hits = await find_memories_v1(session, find_req)

    records = []
    themes = set()
    risks = []
    for record, score in hits:
        records.append(
            {
                "id": record.id,
                "title": record.title,
                "entity_type": record.entity_type,
                "excerpt": record.content[:300] + "..."
                if len(record.content) > 300
                else record.content,
                "relevance": score,
            }
        )
        for tag in record.tags:
            themes.add(tag)
        if record.entity_type.lower() == "risk":
            risks.append(record.content)

    summary = (
        f"OpenBrain found {len(records)} relevant memories for query: '{req.query}'."
    )
    return MemoryGetContextResponse(
        query=req.query,
        summary=summary,
        records=records,
        themes=list(themes)[:10],
        risks=risks[:5],
    )
