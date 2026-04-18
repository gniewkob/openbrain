"""
Memory write operations with circular imports fixed.
Refactored to reduce cyclomatic complexity.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .crud_common import (
    STATUS_DUPLICATE,
    STATUS_SUPERSEDED,
    _audit,
    _can_hard_delete,
    _record_matches_existing,
    _requires_append_only,
    _to_out,
    _to_record,
)
from .embed import get_embedding, EMBED_MAX_CHARS
from .memory_reads import get_memory, get_memory_raw
from .models import AuditLog, DomainEnum, Memory
from .schemas import (
    BatchResultItem,
    BuildTestDataCleanupResponse,
    BuildTestDataCleanupSkip,
    BulkUpsertResult,
    MaintenanceAction,
    MaintenanceReport,
    MaintenanceRequest,
    MemoryCreate,
    MemoryOut,
    MemoryRelations,
    MemoryUpdate,
    MemoryUpsertItem,
    MemoryWriteManyRequest,
    MemoryWriteManyResponse,
    MemoryWriteRecord,
    MemoryWriteRequest,
    MemoryWriteResponse,
    WriteMode,
)

log = structlog.get_logger()


def _session_add(session: AsyncSession, obj: Any) -> None:
    session.add(obj)


def _validate_corporate_domain(
    rec: MemoryWriteRecord,
    mode: WriteMode,
) -> tuple[WriteMode, list[str]]:
    """
    Validate corporate domain requirements.

    Returns:
        Tuple of (updated_mode, error_messages)
    """
    errors = []

    if mode == WriteMode.upsert:
        mode = WriteMode.append_version
    elif mode == WriteMode.update_only:
        errors.append(
            "Corporate domain does not support 'update_only'. Use 'append_version'."
        )

    if not rec.owner:
        errors.append("Owner is required for corporate domain.")

    if not rec.match_key:
        errors.append(
            "match_key is required for corporate domain — ensures "
            "idempotency on append-only records."
        )

    return mode, errors


def _validate_write_mode(
    mode: WriteMode,
    existing: Memory | None,
    match_key: str | None,
) -> list[str]:
    """
    Validate write mode constraints.

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if mode == WriteMode.create_only and existing:
        errors.append(f"Record with match_key '{match_key}' already exists.")

    if mode == WriteMode.update_only and not existing:
        errors.append(f"No active record found for match_key '{match_key}'.")

    return errors


async def _find_existing_memory(
    session: AsyncSession,
    match_key: str | None,
) -> Memory | None:
    """Find existing active memory by match_key."""
    if not match_key:
        return None

    stmt = (
        select(Memory)
        .where(Memory.match_key == match_key, Memory.status == "active")
        .with_for_update()
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


def _log_duplicate_risk(rec: MemoryWriteRecord) -> None:
    """Log warning for duplicate risk writes."""
    if not rec.match_key and rec.domain != "corporate":
        log.warning(
            "duplicate_risk_write",
            domain=rec.domain,
            entity_type=rec.entity_type,
            owner=rec.owner,
            hint="Provide match_key for idempotent writes",
        )


def _warn_if_truncated(content: str, *, domain: str, entity_type: str) -> str | None:
    """
    Log a warning and return a warning message if content exceeds EMBED_MAX_CHARS.

    Returns the warning string (to append to response.warnings), or None if no warning.
    """
    if len(content) <= EMBED_MAX_CHARS:
        return None
    log.warning(
        "write_content_will_be_truncated",
        content_len=len(content),
        embed_max_chars=EMBED_MAX_CHARS,
        domain=domain,
        entity_type=entity_type,
    )
    return (
        f"Content ({len(content)} chars) exceeds embedding limit "
        f"({EMBED_MAX_CHARS} chars); only the first {EMBED_MAX_CHARS} chars "
        "will be indexed for vector search."
    )


def _build_memory_metadata(
    rec: MemoryWriteRecord,
    actor: str,
    append_only_policy: bool,
    previous_id: str | None = None,
    root_id: str | None = None,
) -> dict[str, Any]:
    """Build metadata dictionary for memory record."""
    return {
        "title": rec.title,
        "tenant_id": rec.tenant_id,
        "custom_fields": rec.custom_fields,
        "updated_by": actor,
        "source": rec.source.model_dump(),
        "governance": {
            "mutable": not append_only_policy,
            "append_only": append_only_policy,
        },
        "previous_id": previous_id,
        "root_id": root_id,
    }


async def _create_new_memory(
    session: AsyncSession,
    rec: MemoryWriteRecord,
    actor: str,
    content_hash: str,
    append_only_policy: bool,
    _commit: bool,
) -> MemoryWriteResponse:
    """Create a new memory record."""
    embedding = await get_embedding(rec.content)

    memory = Memory(  # type: ignore[call-arg]
        domain=rec.domain,
        entity_type=rec.entity_type,
        content=rec.content,
        embedding=embedding,
        owner=rec.owner,
        tenant_id=rec.tenant_id,
        created_by=actor,
        status="active",
        version=1,
        sensitivity=rec.sensitivity,
        tags=rec.tags,
        relations=rec.relations.model_dump(),
        obsidian_ref=rec.obsidian_ref,
        content_hash=content_hash,
        match_key=rec.match_key,
        metadata_=_build_memory_metadata(rec, actor, append_only_policy),
    )

    _session_add(session, memory)
    await session.flush()

    memory.metadata_ = {
        **(memory.metadata_ or {}),
        "previous_id": None,
        "root_id": memory.id,
    }

    await _audit(
        session,
        "create",
        memory.id,
        actor=actor,
        tool_name="memory.write",
        meta={"domain": rec.domain},
    )

    if _commit:
        await session.commit()
        await session.refresh(memory)
    else:
        await session.flush()

    return MemoryWriteResponse(status="created", record=_to_record(memory))


async def _version_memory(
    session: AsyncSession,
    existing: Memory,
    rec: MemoryWriteRecord,
    actor: str,
    content_hash: str,
    _commit: bool,
) -> MemoryWriteResponse:
    """Create a new version of an existing memory."""
    new_embedding = await get_embedding(rec.content)

    # Supersede old record first to release the unique-active constraint
    # before inserting the new version with the same match_key.
    existing_id = existing.id
    existing.status = "superseded"
    await session.flush()

    new_memory = Memory(  # type: ignore[call-arg]
        domain=existing.domain,
        entity_type=rec.entity_type,
        content=rec.content,
        embedding=new_embedding,
        owner=rec.owner or existing.owner,
        tenant_id=rec.tenant_id
        or existing.tenant_id
        or existing.metadata_.get("tenant_id"),
        created_by=existing.created_by,
        status="active",
        version=existing.version + 1,
        sensitivity=rec.sensitivity,
        tags=rec.tags,
        relations=rec.relations.model_dump(),
        obsidian_ref=rec.obsidian_ref or existing.obsidian_ref,
        content_hash=content_hash,
        match_key=existing.match_key,
        metadata_={
            "title": rec.title,
            "tenant_id": rec.tenant_id
            or existing.tenant_id
            or existing.metadata_.get("tenant_id"),
            "custom_fields": rec.custom_fields
            or existing.metadata_.get("custom_fields", {}),
            "updated_by": actor,
            "previous_id": existing_id,
            "root_id": existing.metadata_.get("root_id") or existing_id,
            "source": rec.source.model_dump(),
            "governance": existing.metadata_.get("governance", {}),
        },
    )

    _session_add(session, new_memory)
    await session.flush()

    existing.superseded_by = new_memory.id

    await _audit(
        session,
        "version",
        new_memory.id,
        actor=actor,
        tool_name="memory.write",
        meta={"prev_id": existing.id, "reason": "content_update"},
    )

    if _commit:
        await session.commit()
        await session.refresh(new_memory)
    else:
        await session.flush()

    return MemoryWriteResponse(status="versioned", record=_to_record(new_memory))


async def _update_memory(
    session: AsyncSession,
    existing: Memory,
    rec: MemoryWriteRecord,
    actor: str,
    content_hash: str,
    _commit: bool,
) -> MemoryWriteResponse:
    """Update an existing memory in place."""
    new_embedding = await get_embedding(rec.content)

    existing.content = rec.content
    existing.content_hash = content_hash
    existing.embedding = new_embedding
    existing.owner = rec.owner
    existing.tenant_id = rec.tenant_id
    existing.tags = rec.tags
    existing.relations = rec.relations.model_dump()
    existing.obsidian_ref = rec.obsidian_ref
    existing.entity_type = rec.entity_type
    existing.sensitivity = rec.sensitivity
    existing.metadata_ = {
        **(existing.metadata_ or {}),
        "title": rec.title,
        "tenant_id": rec.tenant_id,
        "custom_fields": rec.custom_fields,
        "updated_by": actor,
        "source": rec.source.model_dump(),
    }

    domain_val = (
        existing.domain.value if hasattr(existing.domain, "value") else existing.domain
    )
    await _audit(
        session,
        "update",
        existing.id,
        actor=actor,
        tool_name="memory.write",
        meta={"domain": domain_val},
    )

    if _commit:
        await session.commit()
        await session.refresh(existing)
    else:
        await session.flush()

    return MemoryWriteResponse(status="updated", record=_to_record(existing))


async def handle_memory_write(
    session: AsyncSession,
    request: MemoryWriteRequest,
    actor: str = "agent",
    _commit: bool = True,
) -> MemoryWriteResponse:
    """
    Handle single memory write with domain-aware governance.

    Args:
        session: Database session
        request: Memory write request containing record and write mode
        actor: Actor performing the write (default: "agent")
        _commit: Whether to commit transaction (for batch operations)

    Returns:
        MemoryWriteResponse with status and record info

    Raises:
        ValueError: For invalid write operations
    """
    rec = request.record
    mode = request.write_mode
    domain = rec.domain
    append_only_policy = _requires_append_only(domain, rec.entity_type)

    # Validate corporate domain requirements
    if domain == "corporate":
        mode, errors = _validate_corporate_domain(rec, mode)
        if errors:
            return MemoryWriteResponse(status="failed", errors=errors)

    # Find existing record
    existing = await _find_existing_memory(session, rec.match_key)

    # Validate write mode
    mode_errors = _validate_write_mode(mode, existing, rec.match_key)
    if mode_errors:
        return MemoryWriteResponse(status="failed", errors=mode_errors)

    # Compute content hash
    from .models import compute_hash

    content_hash = compute_hash(rec.content)

    # Log duplicate risk
    _log_duplicate_risk(rec)

    # Warn if content will be truncated during embedding
    _truncation_warning = _warn_if_truncated(
        rec.content, domain=domain, entity_type=rec.entity_type
    )

    # Create new memory if none exists
    if not existing:
        result = await _create_new_memory(
            session, rec, actor, content_hash, append_only_policy, _commit
        )
        if _truncation_warning and result.status != "failed":
            result.warnings.append(_truncation_warning)
        return result

    # Skip if content hasn't changed
    if _record_matches_existing(existing, rec, content_hash):
        return MemoryWriteResponse(status="skipped", record=_to_record(existing))

    # Version or update based on mode and policy
    if mode == WriteMode.append_version or append_only_policy:
        result = await _version_memory(
            session, existing, rec, actor, content_hash, _commit
        )
        if _truncation_warning and result.status != "failed":
            result.warnings.append(_truncation_warning)
        return result

    result = await _update_memory(session, existing, rec, actor, content_hash, _commit)
    if _truncation_warning and result.status != "failed":
        result.warnings.append(_truncation_warning)
    return result


# Keep the rest of the file (handle_memory_write_many, etc.)
# Copy from original file...
async def _prefetch_embeddings(records: list[Any]) -> None:
    """Warm the LRU embedding cache in parallel before batch processing."""
    if records:
        await asyncio.gather(
            *(get_embedding(r.content) for r in records), return_exceptions=True
        )


async def _batch_lookup_match_keys(
    session: AsyncSession, records: list[Any]
) -> dict[str, str | None]:
    """Single query to map match_key → existing memory ID (avoids N+1)."""
    match_keys = [r.match_key for r in records if r.match_key]
    if not match_keys:
        return {}
    stmt = select(Memory.match_key, Memory.id).where(
        Memory.match_key.in_(match_keys), Memory.status == "active"
    )
    result = await session.execute(stmt)
    return {row[0]: row[1] for row in result.all()}


def _compute_overall_status(summary: dict[str, Any], total: int) -> str:
    """Derive batch overall status from per-record summary counts."""
    if summary["failed"] == 0:
        return "success"
    if summary["failed"] < total:
        return "partial_success"
    return "failed"


async def handle_memory_write_many(
    session: AsyncSession,
    request: MemoryWriteManyRequest,
    actor: str = "agent",
) -> MemoryWriteManyResponse:
    """
    Batch write many memories with optimized batch lookup for match_keys.
    Reduces N+1 queries to single batch query.
    """
    results = []
    summary = {
        "received": len(request.records),
        "created": 0,
        "updated": 0,
        "versioned": 0,
        "skipped": 0,
        "failed": 0,
    }
    atomic = request.atomic

    await _prefetch_embeddings(request.records)
    existing_id_map = await _batch_lookup_match_keys(session, request.records)

    async def _process_records(commit_each: bool) -> None:
        for index, record in enumerate(request.records):
            try:
                existing_id = (
                    existing_id_map.get(record.match_key) if record.match_key else None
                )
                res = await handle_memory_write(
                    session,
                    MemoryWriteRequest(record=record, write_mode=request.write_mode),
                    actor=actor,
                    _commit=commit_each,
                )
                results.append(
                    BatchResultItem(
                        input_index=index,
                        status=res.status,
                        record_id=res.record.id if res.record else None,
                        previous_record_id=existing_id
                        if res.status in {"updated", "versioned", "skipped"}
                        else None,
                        match_key=record.match_key,
                        warnings=res.warnings,
                        error=res.errors[0] if res.errors else None,
                    )
                )
                summary[res.status] = summary.get(res.status, 0) + 1
            except Exception as exc:
                log.warning(
                    "batch_record_failed",
                    input_index=index,
                    match_key=record.match_key,
                    error=str(exc),
                )
                results.append(
                    BatchResultItem(
                        input_index=index,
                        status="failed",
                        match_key=record.match_key,
                        error=str(exc),
                    )
                )
                summary["failed"] += 1
                if atomic:
                    raise
                await session.rollback()

    if atomic:
        try:
            await _process_records(commit_each=False)
            await session.commit()
        except Exception as exc:
            log.error("batch_atomic_operation_failed", error=str(exc))
            await session.rollback()
            return MemoryWriteManyResponse(
                status="failed", summary=summary, results=results
            )
    else:
        await _process_records(commit_each=True)

    overall = _compute_overall_status(summary, len(request.records))
    return MemoryWriteManyResponse(status=overall, summary=summary, results=results)  # type: ignore[arg-type]


async def store_memory(
    session: AsyncSession, data: MemoryCreate, actor: str = "agent"
) -> MemoryOut:
    """
    Store a new memory using the write pipeline.

    Args:
        session: Database session
        data: Memory creation data
        actor: Actor identifier for audit

    Returns:
        Created memory output

    Raises:
        ValueError: If write fails
    """
    write_record = MemoryWriteRecord(
        content=data.content,
        domain=data.domain,
        entity_type=data.entity_type,
        owner=data.owner,
        tenant_id=data.tenant_id,
        tags=data.tags,
        match_key=data.match_key,
        obsidian_ref=data.obsidian_ref,
        sensitivity=data.sensitivity,  # type: ignore[arg-type]
        custom_fields=data.custom_fields,
    )
    write_func = handle_memory_write
    res = await write_func(
        session,
        MemoryWriteRequest(record=write_record, write_mode=WriteMode.upsert),
        actor=actor,
    )
    if res.status == "failed":
        raise ValueError(f"Write failed: {res.errors}")
    assert res.record is not None
    return _to_out(await get_memory_raw(session, res.record.id))


async def store_memories_bulk(
    session: AsyncSession, items: list[MemoryCreate]
) -> list[MemoryOut]:
    """Bulk-write multiple new memories using upsert mode and return their output records."""
    records = [
        MemoryWriteRecord(
            content=item.content,
            domain=item.domain,
            entity_type=item.entity_type,
            owner=item.owner,
            tenant_id=item.tenant_id,
            tags=item.tags,
            match_key=item.match_key,
            obsidian_ref=item.obsidian_ref,
            sensitivity=item.sensitivity,  # type: ignore[arg-type]
            custom_fields=item.custom_fields,
            relations=MemoryRelations(**(item.relations or {})),
        )
        for item in items
    ]
    write_many_func = handle_memory_write_many
    res = await write_many_func(
        session, MemoryWriteManyRequest(records=records, write_mode=WriteMode.upsert)
    )
    ids = [result.record_id for result in res.results if result.record_id]
    if not ids:
        return []
    stmt = select(Memory).where(Memory.id.in_(ids))
    result = await session.execute(stmt)
    id_to_mem = {memory.id: _to_out(memory) for memory in result.scalars().all()}
    return [
        id_to_mem[result.record_id]
        for result in res.results
        if result.record_id and result.record_id in id_to_mem
    ]


def _build_update_write_record(memory: Memory, data: MemoryUpdate) -> MemoryWriteRecord:
    """Build a MemoryWriteRecord that merges current memory state with patch data."""
    metadata = memory.metadata_ or {}
    return MemoryWriteRecord(
        match_key=memory.match_key,
        content=data.content if data.content is not None else memory.content,
        domain=memory.domain.value,
        entity_type=memory.entity_type,
        title=data.title if data.title is not None else metadata.get("title"),
        owner=data.owner if data.owner is not None else memory.owner,
        tenant_id=data.tenant_id
        if data.tenant_id is not None
        else (memory.tenant_id or metadata.get("tenant_id")),
        tags=data.tags if data.tags is not None else (memory.tags or []),
        relations=MemoryRelations(
            **(
                data.relations
                if data.relations is not None
                else (memory.relations or {})
            )
        ),
        obsidian_ref=data.obsidian_ref
        if data.obsidian_ref is not None
        else memory.obsidian_ref,
        sensitivity=data.sensitivity if data.sensitivity else memory.sensitivity,  # type: ignore[arg-type]
        custom_fields=data.custom_fields
        if data.custom_fields is not None
        else (metadata.get("custom_fields") or {}),
    )


async def update_memory(
    session: AsyncSession, memory_id: str, data: MemoryUpdate, actor: str = "agent"
) -> MemoryOut | None:
    """Patch an existing memory record, appending a version for corporate domain."""
    stmt = select(Memory).where(Memory.id == memory_id)
    res = await session.execute(stmt)
    memory = res.scalar_one_or_none()
    if not memory:
        return None

    write_record = _build_update_write_record(memory, data)
    write_mode = (
        WriteMode.append_version
        if _requires_append_only(memory.domain, memory.entity_type)
        else WriteMode.upsert
    )
    res_v1 = await handle_memory_write(
        session,
        MemoryWriteRequest(record=write_record, write_mode=write_mode),
        actor=actor,
    )
    if res_v1.status == "failed":
        raise ValueError(f"Update failed: {'; '.join(res_v1.errors)}")
    if res_v1.status == "skipped":
        return _to_out(memory)
    if res_v1.record:
        return await get_memory(session, res_v1.record.id)
    return None


async def delete_memory(
    session: AsyncSession, memory_id: str, actor: str = "agent"
) -> bool:
    """Hard-delete a memory; raises ValueError for append-only (corporate) records."""
    stmt = select(Memory).where(Memory.id == memory_id)
    result = await session.execute(stmt)
    memory = result.scalar_one_or_none()
    if memory is None:
        return False
    if not _can_hard_delete(memory.domain, memory.entity_type):
        raise ValueError("Cannot hard-delete append-only memories.")
    await _audit(
        session,
        "delete",
        memory.id,
        actor=actor,
        tool_name="memory.delete",
        meta={
            "domain": memory.domain.value
            if hasattr(memory.domain, "value")
            else memory.domain,
            "entity_type": memory.entity_type,
            "owner": memory.owner,
            "tenant_id": memory.tenant_id or (memory.metadata_ or {}).get("tenant_id"),
            "version": memory.version,
        },
    )
    await session.delete(memory)
    await session.commit()
    return True


def _classify_bulk_results(
    results: list[BatchResultItem],
    id_to_mem: dict[str, Any],
) -> tuple[list[Any], list[Any], list[Any]]:
    """Classify bulk write results into inserted, updated, and skipped lists."""
    inserted = []
    updated = []
    skipped = []
    for result in results:
        memory = id_to_mem.get(result.record_id) if result.record_id else None
        if result.status == "created" and memory:
            inserted.append(memory)
        elif result.status in {"updated", "versioned"} and memory:
            updated.append(memory)
        elif result.status == "skipped":
            skipped.append(result.record_id or "")
    return inserted, updated, skipped


async def upsert_memories_bulk(
    session: AsyncSession, items: list[MemoryUpsertItem]
) -> BulkUpsertResult:
    """Upsert a batch of memories keyed by match_key; all items must have match_key set."""
    missing_match_keys = [
        str(index) for index, item in enumerate(items) if not item.match_key
    ]
    if missing_match_keys:
        raise ValueError(
            "bulk-upsert requires match_key for every record; missing at indexes: "
            + ", ".join(missing_match_keys)
        )
    records = [
        MemoryWriteRecord(
            content=item.content,
            domain=item.domain,
            entity_type=item.entity_type,
            owner=item.owner,
            tenant_id=item.tenant_id,
            tags=item.tags,
            match_key=item.match_key,
            obsidian_ref=item.obsidian_ref,
            sensitivity=item.sensitivity,  # type: ignore[arg-type]
            custom_fields=item.custom_fields,
        )
        for item in items
    ]
    write_many_func = handle_memory_write_many
    res = await write_many_func(
        session, MemoryWriteManyRequest(records=records, write_mode=WriteMode.upsert)
    )
    ids = [
        result.record_id
        for result in res.results
        if result.record_id and result.status in {"created", "updated", "versioned"}
    ]
    if ids:
        stmt = select(Memory).where(Memory.id.in_(ids))
        result = await session.execute(stmt)
        id_to_mem = {memory.id: _to_out(memory) for memory in result.scalars().all()}
    else:
        id_to_mem = {}

    inserted, updated, skipped = _classify_bulk_results(res.results, id_to_mem)
    return BulkUpsertResult(inserted=inserted, updated=updated, skipped=skipped)


async def run_maintenance(
    session: AsyncSession, req: MaintenanceRequest, actor: str = "agent"
) -> MaintenanceReport:
    """Run maintenance with a configurable timeout (MAINTENANCE_TIMEOUT_S, default 300s)."""
    timeout_s = float(os.environ.get("MAINTENANCE_TIMEOUT_S", "300"))
    async with asyncio.timeout(timeout_s):
        return await _run_maintenance_inner(session, req, actor)


async def _process_duplicates(
    session: AsyncSession,
    dedup_threshold: float,
    total: int,
    dry_run: bool,
) -> tuple[list[MaintenanceAction], int]:
    """Find and remediate exact duplicate memories. Returns (actions, dedup_count)."""
    actions: list[MaintenanceAction] = []
    dedup_count = 0

    if dedup_threshold <= 0 or total <= 1:
        return actions, dedup_count

    dup_groups_stmt = (
        select(Memory.content_hash, Memory.entity_type, Memory.domain)
        .where(Memory.status == "active", Memory.content_hash.isnot(None))
        .group_by(Memory.content_hash, Memory.entity_type, Memory.domain)
        .having(func.count(Memory.id) > 1)
    )
    dup_groups = (await session.execute(dup_groups_stmt)).all()

    for content_hash, entity_type, domain in dup_groups:
        members_stmt = (
            select(Memory)
            .where(
                Memory.content_hash == content_hash,
                Memory.entity_type == entity_type,
                Memory.domain == domain,
                Memory.status == "active",
            )
            .order_by(Memory.created_at.asc())
        )
        members = (await session.execute(members_stmt)).scalars().all()
        canonical = members[0]
        for duplicate in members[1:]:
            dedup_count += 1
            actions.append(
                MaintenanceAction(
                    action="dedup",
                    memory_id=duplicate.id,
                    detail=f"Exact duplicate of {canonical.id}",
                )
            )
            if not dry_run:
                if _requires_append_only(duplicate.domain, duplicate.entity_type):
                    duplicate.status = STATUS_DUPLICATE
                    duplicate.metadata_ = {
                        **(duplicate.metadata_ or {}),
                        "duplicate_of": canonical.id,
                        "remediated_at": datetime.now().isoformat(),
                    }
                    actions.append(
                        MaintenanceAction(
                            action="dedup_remediate",
                            memory_id=duplicate.id,
                            detail=(
                                f"Exact duplicate of {canonical.id} "
                                f"marked as duplicate via "
                                f"governance-safe remediation (append-only)"
                            ),
                        )
                    )
                else:
                    duplicate.status = STATUS_SUPERSEDED
                    duplicate.superseded_by = canonical.id

    return actions, dedup_count


async def _normalize_owners(
    session: AsyncSession,
    normalize_owners: dict[str, str] | None,
    dry_run: bool,
) -> tuple[list[MaintenanceAction], int]:
    """Normalize owner names in memories. Returns (actions, owners_normalized_count)."""
    actions: list[MaintenanceAction] = []
    owners_norm = 0

    if not normalize_owners:
        return actions, owners_norm

    old_owners = list(normalize_owners.keys())
    norm_stmt = select(Memory).where(
        Memory.status == "active", Memory.owner.in_(old_owners)
    )
    norm_memories = (await session.execute(norm_stmt)).scalars().all()
    for memory in norm_memories:
        new_owner = normalize_owners[memory.owner]
        actions.append(
            MaintenanceAction(
                action="normalize_owner",
                memory_id=memory.id,
                detail=f"'{memory.owner}' -> '{new_owner}'",
            )
        )
        if not dry_run:
            if _requires_append_only(memory.domain, memory.entity_type):
                actions.append(
                    MaintenanceAction(
                        action="policy_skip",
                        memory_id=memory.id,
                        detail="Skipped owner normalization for append-only memory",
                    )
                )
                continue
            memory.owner = new_owner
            owners_norm += 1

    return actions, owners_norm


async def _fix_superseded_links(
    session: AsyncSession,
    dry_run: bool,
) -> tuple[list[MaintenanceAction], int]:
    """Repair broken superseded_by links. Returns (actions, links_fixed_count)."""
    actions: list[MaintenanceAction] = []
    links_fixed = 0

    active_ids_result = await session.execute(
        select(Memory.id).where(Memory.status == "active")
    )
    active_ids = {row[0] for row in active_ids_result.all()}
    superseded_stmt = select(Memory).where(
        Memory.superseded_by.isnot(None), Memory.status == "superseded"
    )
    superseded_memories = (await session.execute(superseded_stmt)).scalars().all()
    for memory in superseded_memories:
        if memory.superseded_by and memory.superseded_by not in active_ids:
            links_fixed += 1
            actions.append(
                MaintenanceAction(
                    action="fix_link",
                    memory_id=memory.id,
                    detail=f"superseded_by {memory.superseded_by} not found in active",
                )
            )
            if not dry_run:
                if _requires_append_only(memory.domain, memory.entity_type):
                    actions.append(
                        MaintenanceAction(
                            action="policy_skip",
                            memory_id=memory.id,
                            detail="Skipped supersession link repair for append-only memory",
                        )
                    )
                    continue
                memory.superseded_by, memory.status = None, "active"

    return actions, links_fixed


async def _run_maintenance_inner(
    session: AsyncSession, req: MaintenanceRequest, actor: str = "agent"
) -> MaintenanceReport:
    total_result = await session.execute(
        select(func.count(Memory.id)).where(Memory.status == "active")
    )
    total = total_result.scalar_one()

    dup_actions, dedup_count = await _process_duplicates(
        session=session,
        dedup_threshold=req.dedup_threshold,
        total=total,
        dry_run=req.dry_run,
    )
    owner_actions, owners_norm = await _normalize_owners(
        session=session,
        normalize_owners=req.normalize_owners,
        dry_run=req.dry_run,
    )
    if req.fix_superseded_links:
        link_actions, links_fixed = await _fix_superseded_links(
            session=session,
            dry_run=req.dry_run,
        )
    else:
        link_actions, links_fixed = [], 0

    actions = dup_actions + owner_actions + link_actions
    report = MaintenanceReport(
        dry_run=req.dry_run,
        actions=actions,
        total_scanned=total,
        dedup_found=dedup_count,
        owners_normalized=owners_norm,
        links_fixed=links_fixed,
    )

    if req.dry_run:
        await session.commit()
        return report

    audit_entry = AuditLog(  # type: ignore[call-arg]
        operation="maintain",
        tool_name="memory.maintain",
        memory_id=None,
        actor=actor,
        meta={
            "dry_run": req.dry_run,
            "total_scanned": total,
            "dedup_found": dedup_count,
            "owners_normalized": owners_norm,
            "links_fixed": links_fixed,
            "actions": [action.model_dump() for action in actions],
        },
    )
    _session_add(session, audit_entry)
    await session.flush()
    report.report_id = audit_entry.id
    await session.commit()
    return report


async def cleanup_build_test_data(
    session: AsyncSession,
    *,
    dry_run: bool = True,
    limit: int = 100,
    actor: str = "agent",
) -> BuildTestDataCleanupResponse:
    """
    Cleanup flow for build-domain test data records.

    Default mode is dry-run. Execution mode deletes only candidate records that pass
    existing hard-delete policy checks.
    """
    is_test_data = (
        func.coalesce(Memory.metadata_["test_data"].astext, "false") == "true"
    )
    candidates_stmt = (
        select(Memory.id)
        .where(
            Memory.domain == DomainEnum.build,
            Memory.status == "active",
            is_test_data,
        )
        .order_by(Memory.updated_at.desc())
        .limit(limit)
    )
    candidates_result = await session.execute(candidates_stmt)
    candidate_ids = [str(row.id) for row in candidates_result.all()]

    if dry_run:
        return BuildTestDataCleanupResponse(
            dry_run=True,
            scanned=len(candidate_ids),
            candidates_count=len(candidate_ids),
            deleted_count=0,
            skipped_count=0,
            candidate_ids=candidate_ids,
            deleted_ids=[],
            skipped=[],
        )

    deleted_ids: list[str] = []
    skipped: list[BuildTestDataCleanupSkip] = []
    for memory_id in candidate_ids:
        try:
            deleted = await delete_memory(session, memory_id, actor=actor)
        except ValueError as exc:
            skipped.append(BuildTestDataCleanupSkip(id=memory_id, reason=str(exc)))
            continue
        if deleted:
            deleted_ids.append(memory_id)

    return BuildTestDataCleanupResponse(
        dry_run=False,
        scanned=len(candidate_ids),
        candidates_count=len(candidate_ids),
        deleted_count=len(deleted_ids),
        skipped_count=len(skipped),
        candidate_ids=candidate_ids,
        deleted_ids=deleted_ids,
        skipped=skipped,
    )
