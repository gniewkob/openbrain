from __future__ import annotations

from datetime import datetime
from inspect import isawaitable

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
from .embed import get_embedding
from .memory_reads import get_memory, get_memory_raw
from .models import AuditLog, Memory
from .schemas import (
    BatchResultItem,
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


# Direct function references - no circular imports
async def _get_embedding_compat(text: str):
    """Get embedding using local import."""
    return await get_embedding(text)


async def _audit_compat(*args, **kwargs):
    """Audit using direct reference."""
    return await _audit(*args, **kwargs)


def _session_add(session: AsyncSession, obj) -> None:
    maybe_result = session.add(obj)
    if isawaitable(maybe_result):
        return maybe_result
    return None


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

    if domain == "corporate":
        if mode == WriteMode.upsert:
            mode = WriteMode.append_version
        elif mode == WriteMode.update_only:
            return MemoryWriteResponse(
                status="failed",
                errors=["Corporate domain does not support 'update_only'. Use 'append_version'."],
            )
        if not rec.owner:
            return MemoryWriteResponse(status="failed", errors=["Owner is required for corporate domain."])
        if not rec.match_key:
            return MemoryWriteResponse(
                status="failed",
                errors=["match_key is required for corporate domain — ensures idempotency on append-only records."],
            )

    existing = None
    if rec.match_key:
        stmt = (
            select(Memory)
            .where(Memory.match_key == rec.match_key, Memory.status == "active")
            .with_for_update()
        )
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

    if mode == WriteMode.create_only and existing:
        return MemoryWriteResponse(status="failed", errors=[f"Record with match_key '{rec.match_key}' already exists."])
    if mode == WriteMode.update_only and not existing:
        return MemoryWriteResponse(status="failed", errors=[f"No active record found for match_key '{rec.match_key}'."])

    from .models import compute_hash  # local import keeps helper module smaller

    content_hash = compute_hash(rec.content)

    if not rec.match_key and rec.domain != "corporate":
        log.warning(
            "duplicate_risk_write",
            domain=rec.domain,
            entity_type=rec.entity_type,
            owner=rec.owner,
            hint="Provide match_key for idempotent writes",
        )

    if not existing:
        embedding = await _get_embedding_compat(rec.content)
        memory = Memory(
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
            metadata_={
                "title": rec.title,
                "tenant_id": rec.tenant_id,
                "custom_fields": rec.custom_fields,
                "updated_by": actor,
                "source": rec.source.model_dump(),
                "governance": {"mutable": not append_only_policy, "append_only": append_only_policy},
            },
        )
        maybe_add = _session_add(session, memory)
        if maybe_add is not None:
            await maybe_add
        await session.flush()
        memory.metadata_ = {**(memory.metadata_ or {}), "previous_id": None, "root_id": memory.id}

        if domain == "corporate":
            await _audit_compat(session, "create", memory.id, actor=actor, tool_name="memory.write")

        if _commit:
            await session.commit()
            await session.refresh(memory)
        else:
            await session.flush()
        return MemoryWriteResponse(status="created", record=_to_record(memory))

    if _record_matches_existing(existing, rec, content_hash):
        return MemoryWriteResponse(status="skipped", record=_to_record(existing))

    if mode == WriteMode.append_version or append_only_policy:
        new_embedding = await _get_embedding_compat(rec.content)
        new_memory = Memory(
            domain=existing.domain,
            entity_type=rec.entity_type,
            content=rec.content,
            embedding=new_embedding,
            owner=rec.owner or existing.owner,
            tenant_id=rec.tenant_id or existing.tenant_id or existing.metadata_.get("tenant_id"),
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
                "tenant_id": rec.tenant_id or existing.tenant_id or existing.metadata_.get("tenant_id"),
                "custom_fields": rec.custom_fields or existing.metadata_.get("custom_fields", {}),
                "updated_by": actor,
                "previous_id": existing.id,
                "root_id": existing.metadata_.get("root_id") or existing.id,
                "source": rec.source.model_dump(),
                "governance": existing.metadata_.get("governance", {}),
            },
        )
        maybe_add = _session_add(session, new_memory)
        if maybe_add is not None:
            await maybe_add
        await session.flush()

        existing.status = "superseded"
        existing.superseded_by = new_memory.id
        await _audit_compat(
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

    new_embedding = await _get_embedding_compat(rec.content)
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

    if _commit:
        await session.commit()
        await session.refresh(existing)
    else:
        await session.flush()
    return MemoryWriteResponse(status="updated", record=_to_record(existing))


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
    summary = {"received": len(request.records), "created": 0, "updated": 0, "versioned": 0, "skipped": 0, "failed": 0}
    atomic = request.atomic
    
    # Batch lookup: collect all match_keys first to avoid N+1 queries
    match_keys = [r.match_key for r in request.records if r.match_key]
    existing_id_map: dict[str, str | None] = {}
    
    if match_keys:
        # Single query to fetch all existing records by match_key
        batch_lookup_stmt = (
            select(Memory.match_key, Memory.id)
            .where(Memory.match_key.in_(match_keys), Memory.status == "active")
        )
        batch_result = await session.execute(batch_lookup_stmt)
        existing_id_map = {row[0]: row[1] for row in batch_result.all()}

    async def _process_records(commit_each: bool) -> None:
        for index, record in enumerate(request.records):
            try:
                # Use pre-fetched existing_id from batch lookup
                existing_id = existing_id_map.get(record.match_key) if record.match_key else None

                write_func = handle_memory_write
                res = await write_func(
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
                        previous_record_id=existing_id if res.status in {"updated", "versioned", "skipped"} else None,
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
            return MemoryWriteManyResponse(status="failed", summary=summary, results=results)
    else:
        await _process_records(commit_each=True)

    overall = "success" if summary["failed"] == 0 else ("partial_success" if summary["failed"] < len(request.records) else "failed")
    return MemoryWriteManyResponse(status=overall, summary=summary, results=results)


async def store_memory(session: AsyncSession, data: MemoryCreate, actor: str = "agent") -> MemoryOut:
    write_record = MemoryWriteRecord(
        content=data.content,
        domain=data.domain,
        entity_type=data.entity_type,
        owner=data.owner,
        tenant_id=data.tenant_id,
        tags=data.tags,
        match_key=data.match_key,
        obsidian_ref=data.obsidian_ref,
        sensitivity=data.sensitivity,
        custom_fields=data.custom_fields,
    )
    write_func = handle_memory_write
    res = await write_func(session, MemoryWriteRequest(record=write_record, write_mode=WriteMode.upsert), actor=actor)
    if res.status == "failed":
        raise ValueError(f"Write failed: {res.errors}")
    return _to_out(await get_memory_raw(session, res.record.id))


async def store_memories_bulk(session: AsyncSession, items: list[MemoryCreate]) -> list[MemoryOut]:
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
            sensitivity=item.sensitivity,
            custom_fields=item.custom_fields,
            relations=MemoryRelations(**(item.relations or {})),
        )
        for item in items
    ]
    write_many_func = handle_memory_write_many
    res = await write_many_func(session, MemoryWriteManyRequest(records=records, write_mode=WriteMode.upsert))
    ids = [result.record_id for result in res.results if result.record_id]
    if not ids:
        return []
    stmt = select(Memory).where(Memory.id.in_(ids))
    result = await session.execute(stmt)
    id_to_mem = {memory.id: _to_out(memory) for memory in result.scalars().all()}
    return [id_to_mem[result.record_id] for result in res.results if result.record_id and result.record_id in id_to_mem]


async def update_memory(session: AsyncSession, memory_id: str, data: MemoryUpdate, actor: str = "agent") -> MemoryOut | None:
    stmt = select(Memory).where(Memory.id == memory_id)
    res = await session.execute(stmt)
    memory = res.scalar_one_or_none()
    if not memory:
        return None

    metadata = memory.metadata_ or {}
    write_record = MemoryWriteRecord(
        match_key=memory.match_key,
        content=data.content if data.content is not None else memory.content,
        domain=memory.domain.value,
        entity_type=memory.entity_type,
        title=data.title if data.title is not None else metadata.get("title"),
        owner=data.owner if data.owner is not None else memory.owner,
        tenant_id=data.tenant_id if data.tenant_id is not None else (memory.tenant_id or metadata.get("tenant_id")),
        tags=data.tags if data.tags is not None else memory.tags,
        relations=MemoryRelations(**(data.relations if data.relations is not None else (memory.relations or {}))),
        obsidian_ref=data.obsidian_ref if data.obsidian_ref is not None else memory.obsidian_ref,
        sensitivity=data.sensitivity if data.sensitivity else memory.sensitivity,
        custom_fields=data.custom_fields if data.custom_fields is not None else (metadata.get("custom_fields") or {}),
    )
    write_mode = WriteMode.append_version if _requires_append_only(memory.domain, memory.entity_type) else WriteMode.upsert
    write_func = handle_memory_write
    res_v1 = await write_func(session, MemoryWriteRequest(record=write_record, write_mode=write_mode), actor=actor)
    if res_v1.status == "failed":
        raise ValueError(f"Update failed: {'; '.join(res_v1.errors)}")
    if res_v1.status == "skipped":
        return _to_out(memory)
    if res_v1.record:
        return await get_memory(session, res_v1.record.id)
    return None


async def delete_memory(session: AsyncSession, memory_id: str, actor: str = "agent") -> bool:
    stmt = select(Memory).where(Memory.id == memory_id)
    result = await session.execute(stmt)
    memory = result.scalar_one_or_none()
    if memory is None:
        return False
    if not _can_hard_delete(memory.domain, memory.entity_type):
        raise ValueError("Cannot hard-delete append-only memories.")
    await _audit_compat(
        session,
        "delete",
        memory.id,
        actor=actor,
        tool_name="memory.delete",
        meta={
            "domain": memory.domain.value if hasattr(memory.domain, "value") else memory.domain,
            "entity_type": memory.entity_type,
            "owner": memory.owner,
            "tenant_id": memory.tenant_id or (memory.metadata_ or {}).get("tenant_id"),
            "version": memory.version,
        },
    )
    await session.delete(memory)
    await session.commit()
    return True


async def upsert_memories_bulk(session: AsyncSession, items: list[MemoryUpsertItem]) -> BulkUpsertResult:
    missing_match_keys = [str(index) for index, item in enumerate(items) if not item.match_key]
    if missing_match_keys:
        raise ValueError(
            "bulk-upsert requires match_key for every record; missing at indexes: " + ", ".join(missing_match_keys)
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
            sensitivity=item.sensitivity,
            custom_fields=item.custom_fields,
        )
        for item in items
    ]
    write_many_func = handle_memory_write_many
    res = await write_many_func(session, MemoryWriteManyRequest(records=records, write_mode=WriteMode.upsert))
    ids = [result.record_id for result in res.results if result.record_id and result.status in {"created", "updated", "versioned"}]
    if ids:
        stmt = select(Memory).where(Memory.id.in_(ids))
        result = await session.execute(stmt)
        id_to_mem = {memory.id: _to_out(memory) for memory in result.scalars().all()}
    else:
        id_to_mem = {}

    inserted, updated, skipped = [], [], []
    for result in res.results:
        memory = id_to_mem.get(result.record_id) if result.record_id else None
        if result.status == "created" and memory:
            inserted.append(memory)
        elif result.status in {"updated", "versioned"} and memory:
            updated.append(memory)
        elif result.status == "skipped":
            skipped.append(result.record_id or "")
    return BulkUpsertResult(inserted=inserted, updated=updated, skipped=skipped)


async def run_maintenance(session: AsyncSession, req: MaintenanceRequest, actor: str = "agent") -> MaintenanceReport:
    actions: list[MaintenanceAction] = []
    dedup_count, owners_norm, links_fixed = 0, 0, 0

    total_result = await session.execute(select(func.count(Memory.id)).where(Memory.status == "active"))
    total = total_result.scalar_one()

    if req.dedup_threshold > 0 and total > 1:
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
                actions.append(MaintenanceAction(action="dedup", memory_id=duplicate.id, detail=f"Exact duplicate of {canonical.id}"))
                if not req.dry_run:
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
                                detail=f"Exact duplicate of {canonical.id} marked as duplicate via governance-safe remediation (append-only)",
                            )
                        )
                    else:
                        duplicate.status = STATUS_SUPERSEDED
                        duplicate.superseded_by = canonical.id

    if req.normalize_owners:
        old_owners = list(req.normalize_owners.keys())
        norm_stmt = select(Memory).where(Memory.status == "active", Memory.owner.in_(old_owners))
        norm_memories = (await session.execute(norm_stmt)).scalars().all()
        for memory in norm_memories:
            new_owner = req.normalize_owners[memory.owner]
            actions.append(MaintenanceAction(action="normalize_owner", memory_id=memory.id, detail=f"'{memory.owner}' -> '{new_owner}'"))
            if not req.dry_run:
                if _requires_append_only(memory.domain, memory.entity_type):
                    actions.append(MaintenanceAction(action="policy_skip", memory_id=memory.id, detail="Skipped owner normalization for append-only memory"))
                    continue
                memory.owner = new_owner
                owners_norm += 1

    if req.fix_superseded_links:
        active_ids_result = await session.execute(select(Memory.id).where(Memory.status == "active"))
        active_ids = {row[0] for row in active_ids_result.all()}
        superseded_stmt = select(Memory).where(Memory.superseded_by.isnot(None), Memory.status == "superseded")
        superseded_memories = (await session.execute(superseded_stmt)).scalars().all()
        for memory in superseded_memories:
            if memory.superseded_by and memory.superseded_by not in active_ids:
                links_fixed += 1
                actions.append(MaintenanceAction(action="fix_link", memory_id=memory.id, detail=f"superseded_by {memory.superseded_by} not found in active"))
                if not req.dry_run:
                    if _requires_append_only(memory.domain, memory.entity_type):
                        actions.append(MaintenanceAction(action="policy_skip", memory_id=memory.id, detail="Skipped supersession link repair for append-only memory"))
                        continue
                    memory.superseded_by, memory.status = None, "active"

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

    audit_entry = AuditLog(
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
    maybe_add = _session_add(session, audit_entry)
    if maybe_add is not None:
        await maybe_add
    await session.flush()
    report.report_id = audit_entry.id
    await session.commit()
    return report
