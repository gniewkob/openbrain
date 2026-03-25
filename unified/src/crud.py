"""
OpenBrain Unified v2.1 — CRUD Operations.

Memory Platform V1 Engine:
- Unified handle_memory_write for all write operations.
- Strict Domain Governance.
- Idempotency via match_key.
"""
from __future__ import annotations

from typing import Any
from datetime import datetime

import structlog
from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from .embed import get_embedding
from .models import AuditLog, DomainEnum, Memory, compute_hash
from .schemas import (
    BatchResultItem,
    BulkUpsertResult,
    GovernanceMetadata,
    MaintenanceAction,
    MaintenanceReport,
    MaintenanceRequest,
    MemoryCreate,
    MemoryFindRequest,
    MemoryOut,
    MemoryRecord,
    MemoryRelations,
    MemoryUpdate,
    MemoryUpsertItem,
    MemoryWriteManyRequest,
    MemoryWriteManyResponse,
    MemoryWriteRecord,
    MemoryWriteRequest,
    MemoryWriteResponse,
    SearchRequest,
    SearchResult,
    SourceMetadata,
    WriteMode,
)

log = structlog.get_logger()

CORPORATE = DomainEnum.corporate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_record(m: Memory) -> MemoryRecord:
    """Map SQLAlchemy model to canonical MemoryRecord."""
    # Extract V1 fields from metadata if they exist
    meta = m.metadata_ or {}
    source = meta.get("source", {})
    gov = meta.get("governance", {})
    
    return MemoryRecord(
        id=m.id,
        match_key=m.match_key,
        domain=m.domain.value if isinstance(m.domain, DomainEnum) else m.domain,
        entity_type=m.entity_type,
        title=meta.get("title") or m.entity_type, # fallback
        content=m.content,
        summary=meta.get("summary"),
        owner=m.owner,
        tags=m.tags or [],
        relations=MemoryRelations(**(m.relations or {})),
        status=m.status,
        sensitivity=m.sensitivity,
        source=SourceMetadata(**source) if source else SourceMetadata(),
        governance=GovernanceMetadata(**gov) if gov else GovernanceMetadata(),
        obsidian_ref=m.obsidian_ref,
        content_hash=m.content_hash,
        version=m.version,
        superseded_by=m.superseded_by,
        valid_from=m.valid_from,
        created_at=m.created_at,
        updated_at=m.updated_at,
        created_by=m.created_by,
        updated_by=m.created_by, # placeholder
    )

def _to_out(m: Memory) -> MemoryOut:
    """Legacy helper for backward compatibility."""
    return MemoryOut(
        id=m.id,
        domain=m.domain.value if isinstance(m.domain, DomainEnum) else m.domain,
        entity_type=m.entity_type,
        content=m.content,
        owner=m.owner,
        status=m.status,
        version=m.version,
        sensitivity=m.sensitivity,
        superseded_by=m.superseded_by,
        tags=m.tags or [],
        relations=m.relations or {},
        obsidian_ref=m.obsidian_ref,
        content_hash=m.content_hash,
        match_key=m.match_key,
        valid_from=m.valid_from,
        created_at=m.created_at,
        updated_at=m.updated_at,
        created_by=m.created_by,
    )


async def _audit(
    session: AsyncSession,
    operation: str,
    memory_id: str | None,
    actor: str = "agent",
    tool_name: str = "",
    meta: dict | None = None,
) -> None:
    entry = AuditLog(
        operation=operation,
        tool_name=tool_name,
        memory_id=memory_id,
        actor=actor,
        meta=meta or {},
    )
    session.add(entry)


# ---------------------------------------------------------------------------
# V1 UNIFIED ENGINE
# ---------------------------------------------------------------------------

async def handle_memory_write(
    session: AsyncSession, 
    request: MemoryWriteRequest, 
    actor: str = "agent"
) -> MemoryWriteResponse:
    """The canonical write engine for OpenBrain."""
    rec = request.record
    mode = request.write_mode
    domain = rec.domain
    
    # 1. Domain Governance Rules
    if domain == "corporate":
        if mode not in [WriteMode.create_only, WriteMode.append_version]:
            return MemoryWriteResponse(
                status="failed", 
                errors=["Corporate domain requires 'create_only' or 'append_version' modes."]
            )
        if not rec.owner:
            return MemoryWriteResponse(status="failed", errors=["Owner is required for corporate domain."])

    # 2. Match existing record
    existing = None
    if rec.match_key:
        stmt = select(Memory).where(Memory.match_key == rec.match_key, Memory.status == "active")
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

    # 3. Handle Create Only
    if mode == WriteMode.create_only and existing:
        return MemoryWriteResponse(status="failed", errors=[f"Record with match_key '{rec.match_key}' already exists."])

    # 4. Handle Update Only
    if mode == WriteMode.update_only and not existing:
        return MemoryWriteResponse(status="failed", errors=[f"No active record found for match_key '{rec.match_key}'."])

    # 5. Determine Operation: CREATE or UPDATE/VERSION
    content_hash = compute_hash(rec.content)
    
    if not existing:
        # --- CREATE NEW ---
        embedding = await get_embedding(rec.content)
        memory = Memory(
            domain=DomainEnum(rec.domain),
            entity_type=rec.entity_type,
            content=rec.content,
            embedding=embedding,
            owner=rec.owner,
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
                "source": rec.source.model_dump(),
                "governance": {
                    "mutable": rec.domain != "corporate",
                    "append_only": rec.domain == "corporate"
                }
            }
        )
        session.add(memory)
        await session.flush()
        
        if domain == "corporate":
            await _audit(session, "create", memory.id, actor=actor, tool_name="memory.write")
            
        await session.commit()
        await session.refresh(memory)
        return MemoryWriteResponse(status="created", record=_to_record(memory))

    else:
        # --- UPDATE or VERSION ---
        if existing.content_hash == content_hash and mode == WriteMode.upsert:
            # Check if metadata changed (owner, tags, etc)
            changed = (
                existing.owner != rec.owner or 
                existing.tags != rec.tags or 
                existing.obsidian_ref != rec.obsidian_ref
            )
            if not changed:
                return MemoryWriteResponse(status="skipped", record=_to_record(existing))

        if mode == WriteMode.append_version or domain == "corporate":
            # --- CREATE NEW VERSION ---
            new_embedding = await get_embedding(rec.content)
            new_memory = Memory(
                domain=existing.domain,
                entity_type=rec.entity_type,
                content=rec.content,
                embedding=new_embedding,
                owner=rec.owner or existing.owner,
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
                    "source": rec.source.model_dump(),
                    "governance": existing.metadata_.get("governance", {})
                }
            )
            session.add(new_memory)
            await session.flush()
            
            existing.status = "superseded"
            existing.superseded_by = new_memory.id
            
            await _audit(session, "version", new_memory.id, actor=actor, tool_name="memory.write", 
                          meta={"prev_id": existing.id, "reason": "content_update"})
            
            await session.commit()
            await session.refresh(new_memory)
            return MemoryWriteResponse(status="versioned", record=_to_record(new_memory))
        else:
            # --- MUTATE IN PLACE (build/personal) ---
            existing.content = rec.content
            existing.content_hash = content_hash
            existing.embedding = await get_embedding(rec.content)
            existing.owner = rec.owner
            existing.tags = rec.tags
            existing.relations = rec.relations.model_dump()
            existing.obsidian_ref = rec.obsidian_ref
            existing.entity_type = rec.entity_type
            existing.sensitivity = rec.sensitivity
            
            # Update metadata
            meta = existing.metadata_ or {}
            meta["title"] = rec.title
            meta["source"] = rec.source.model_dump()
            existing.metadata_ = meta
            
            await session.commit()
            await session.refresh(existing)
            return MemoryWriteResponse(status="updated", record=_to_record(existing))


async def handle_memory_write_many(
    session: AsyncSession, 
    request: MemoryWriteManyRequest,
    actor: str = "agent"
) -> MemoryWriteManyResponse:
    results = []
    summary = {"received": len(request.records), "created": 0, "updated": 0, "versioned": 0, "skipped": 0, "failed": 0}
    
    for i, rec in enumerate(request.records):
        try:
            res = await handle_memory_write(session, MemoryWriteRequest(record=rec, write_mode=request.write_mode), actor=actor)
            results.append(BatchResultItem(
                input_index=i,
                status=res.status,
                record_id=res.record.id if res.record else None,
                match_key=rec.match_key,
                warnings=res.warnings,
                error=res.errors[0] if res.errors else None
            ))
            summary[res.status] = summary.get(res.status, 0) + 1
        except Exception as e:
            results.append(BatchResultItem(input_index=i, status="failed", error=str(e)))
            summary["failed"] += 1
            
    status = "success" if summary["failed"] == 0 else ("partial_success" if summary["failed"] < len(request.records) else "failed")
    return MemoryWriteManyResponse(status=status, summary=summary, results=results)


# ---------------------------------------------------------------------------
# Legacy compatibility (Stay available for now)
# ---------------------------------------------------------------------------

async def store_memory(session: AsyncSession, data: MemoryCreate) -> MemoryOut:
    """Deprecated: using v1 handle_memory_write internally."""
    write_rec = MemoryWriteRecord(
        content=data.content,
        domain=data.domain,
        entity_type=data.entity_type,
        owner=data.owner,
        tags=data.tags,
        match_key=data.match_key,
        obsidian_ref=data.obsidian_ref,
        sensitivity=data.sensitivity
    )
    res = await handle_memory_write(session, MemoryWriteRequest(record=write_rec, write_mode=WriteMode.upsert))
    if res.status == "failed":
        raise ValueError(f"Write failed: {res.errors}")
    return _to_out(await get_memory_raw(session, res.record.id))

async def get_memory_raw(session: AsyncSession, memory_id: str) -> Memory:
    stmt = select(Memory).where(Memory.id == memory_id)
    res = await session.execute(stmt)
    return res.scalar_one()

async def store_memories_bulk(session: AsyncSession, items: list[MemoryCreate]) -> list[MemoryOut]:
    recs = [MemoryWriteRecord(content=i.content, domain=i.domain, entity_type=i.entity_type, owner=i.owner, tags=i.tags, match_key=i.match_key, obsidian_ref=i.obsidian_ref, sensitivity=i.sensitivity) for i in items]
    res = await handle_memory_write_many(session, MemoryWriteManyRequest(records=recs, write_mode=WriteMode.upsert))
    out = []
    for r in res.results:
        if r.record_id:
            m = await get_memory(session, r.record_id)
            if m: out.append(m)
    return out

async def get_memory(session: AsyncSession, memory_id: str) -> MemoryOut | None:
    stmt = select(Memory).where(Memory.id == memory_id)
    result = await session.execute(stmt)
    m = result.scalar_one_or_none()
    return _to_out(m) if m else None

async def list_memories(session: AsyncSession, filters: dict[str, Any], limit: int = 20) -> list[MemoryOut]:
    stmt = select(Memory)
    if "domain" in filters:
        stmt = stmt.where(Memory.domain == DomainEnum(filters["domain"]))
    if "entity_type" in filters:
        stmt = stmt.where(Memory.entity_type == filters["entity_type"])
    if "status" in filters:
        stmt = stmt.where(Memory.status == filters["status"])
    else:
        stmt = stmt.where(Memory.status != "superseded")
    if "sensitivity" in filters:
        stmt = stmt.where(Memory.sensitivity == filters["sensitivity"])
    if "owner" in filters:
        stmt = stmt.where(Memory.owner == filters["owner"])

    stmt = stmt.order_by(Memory.updated_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return [_to_out(m) for m in result.scalars().all()]

async def search_memories(session: AsyncSession, req: SearchRequest) -> list[tuple[MemoryOut, float]]:
    embedding = await get_embedding(req.query)
    stmt = select(Memory, Memory.embedding.cosine_distance(embedding).label("distance")).where(Memory.status == "active")
    filters = req.filters
    if "domain" in filters:
        stmt = stmt.where(Memory.domain == DomainEnum(filters["domain"]))
    if "entity_type" in filters:
        stmt = stmt.where(Memory.entity_type == filters["entity_type"])
    if "sensitivity" in filters:
        stmt = stmt.where(Memory.sensitivity == filters["sensitivity"])
    stmt = stmt.order_by("distance").limit(req.top_k)
    result = await session.execute(stmt)
    return [(_to_out(row.Memory), float(row.distance)) for row in result.all()]

async def update_memory(session: AsyncSession, memory_id: str, data: MemoryUpdate) -> MemoryOut | None:
    stmt = select(Memory).where(Memory.id == memory_id)
    res = await session.execute(stmt)
    m = res.scalar_one_or_none()
    if not m: return None
    
    write_rec = MemoryWriteRecord(
        content=data.content,
        domain=m.domain.value,
        entity_type=m.entity_type,
        owner=data.owner if data.owner is not None else m.owner,
        tags=data.tags if data.tags is not None else m.tags,
        obsidian_ref=data.obsidian_ref if data.obsidian_ref is not None else m.obsidian_ref,
        sensitivity=data.sensitivity if data.sensitivity else m.sensitivity
    )
    res_v1 = await handle_memory_write(session, MemoryWriteRequest(record=write_rec, write_mode=WriteMode.upsert))
    if res_v1.record:
        return await get_memory(session, res_v1.record.id)
    return None

async def delete_memory(session: AsyncSession, memory_id: str) -> bool:
    stmt = select(Memory).where(Memory.id == memory_id)
    result = await session.execute(stmt)
    m = result.scalar_one_or_none()
    if m is None: return False
    if m.domain == CORPORATE: raise ValueError("Cannot delete corporate memories.")
    await session.delete(m)
    await session.commit()
    return True

async def upsert_memories_bulk(session: AsyncSession, items: list[MemoryUpsertItem]) -> BulkUpsertResult:
    recs = [MemoryWriteRecord(content=i.content, domain=i.domain, entity_type=i.entity_type, owner=i.owner, tags=i.tags, match_key=i.match_key, obsidian_ref=i.obsidian_ref, sensitivity=i.sensitivity) for i in items]
    res = await handle_memory_write_many(session, MemoryWriteManyRequest(records=recs, write_mode=WriteMode.upsert))
    
    inserted, updated, skipped = [], [], []
    for r in res.results:
        m = await get_memory(session, r.record_id) if r.record_id else None
        if r.status == "created" and m: inserted.append(m)
        elif r.status == "updated" and m: updated.append(m)
        elif r.status == "skipped": skipped.append(r.record_id or "")
    return BulkUpsertResult(inserted=inserted, updated=updated, skipped=skipped)

async def export_memories(session: AsyncSession, ids: list[str]) -> list[dict]:
    stmt = select(Memory).where(Memory.id.in_(ids))
    result = await session.execute(stmt)
    memories = result.scalars().all()
    exported = []
    for m in memories:
        out = _to_out(m).model_dump(mode="json")
        if m.sensitivity == "restricted": out["content"] = "[REDACTED — restricted sensitivity]"
        exported.append(out)
    return exported

async def sync_check(session: AsyncSession, obsidian_ref: str, file_hash: str) -> dict[str, str]:
    stmt = select(Memory.content_hash).where(Memory.obsidian_ref == obsidian_ref)
    result = await session.execute(stmt)
    stored_hash = result.scalar_one_or_none()
    if stored_hash is None: return {"status": "missing", "message": "Note not found in index."}
    if stored_hash != file_hash: return {"status": "outdated", "message": "Hash mismatch. Update required."}
    return {"status": "synced", "message": "Note is up to date."}

async def run_maintenance(session: AsyncSession, req: MaintenanceRequest) -> MaintenanceReport:
    actions: list[MaintenanceAction] = []
    stmt = select(Memory).where(Memory.status == "active")
    result = await session.execute(stmt)
    memories = list(result.scalars().all())
    total, dedup_count, owners_norm, links_fixed = len(memories), 0, 0, 0

    if req.dedup_threshold > 0 and len(memories) > 1:
        checked = set()
        for i, m1 in enumerate(memories):
            if m1.id in checked or m1.embedding is None: continue
            for m2 in memories[i + 1 :]:
                if m2.id in checked or m2.embedding is None: continue
                if m1.content_hash == m2.content_hash and m1.entity_type == m2.entity_type:
                    dedup_count += 1
                    actions.append(MaintenanceAction(action="dedup", memory_id=m2.id, detail=f"Exact duplicate of {m1.id}"))
                    if not req.dry_run:
                        m2.status = "superseded"
                        m2.superseded_by = m1.id
                    checked.add(m2.id)

    if req.normalize_owners:
        for m in memories:
            if m.owner in req.normalize_owners:
                new_owner = req.normalize_owners[m.owner]
                actions.append(MaintenanceAction(action="normalize_owner", memory_id=m.id, detail=f"'{m.owner}' -> '{new_owner}'"))
                if not req.dry_run: m.owner = new_owner
                owners_norm += 1

    if req.fix_superseded_links:
        stmt2 = select(Memory).where(Memory.superseded_by.isnot(None), Memory.status == "superseded")
        result2 = await session.execute(stmt2)
        superseded, active_ids = result2.scalars().all(), {m.id for m in memories}
        for m in superseded:
            if m.superseded_by and m.superseded_by not in active_ids:
                links_fixed += 1
                actions.append(MaintenanceAction(action="fix_link", memory_id=m.id, detail=f"superseded_by {m.superseded_by} not found in active"))
                if not req.dry_run: m.superseded_by, m.status = None, "active"

    if not req.dry_run: await session.commit()
    return MaintenanceReport(dry_run=req.dry_run, actions=actions, total_scanned=total, dedup_found=dedup_count, owners_normalized=owners_norm, links_fixed=links_fixed)


# ---------------------------------------------------------------------------
# V1 INTELLIGENCE
# ---------------------------------------------------------------------------

async def find_memories_v1(
    session: AsyncSession, 
    req: MemoryFindRequest
) -> list[tuple[MemoryRecord, float]]:
    """Hybrid search returning canonical MemoryRecords."""
    embedding = await get_embedding(req.query) if req.query else None
    
    if embedding:
        stmt = select(Memory, Memory.embedding.cosine_distance(embedding).label("distance")).where(Memory.status == "active")
    else:
        stmt = select(Memory).where(Memory.status == "active")

    filters = req.filters
    if "domain" in filters:
        domains = filters["domain"] if isinstance(filters["domain"], list) else [filters["domain"]]
        stmt = stmt.where(Memory.domain.in_([DomainEnum(d) for d in domains]))
    if "entity_type" in filters:
        types = filters["entity_type"] if isinstance(filters["entity_type"], list) else [filters["entity_type"]]
        stmt = stmt.where(Memory.entity_type.in_(types))
    if "owner" in filters:
        owners = filters["owner"] if isinstance(filters["owner"], list) else [filters["owner"]]
        stmt = stmt.where(Memory.owner.in_(owners))
    if "tags_any" in filters:
        stmt = stmt.where(Memory.tags.overlap(filters["tags_any"]))

    if embedding and req.sort == "relevance":
        stmt = stmt.order_by("distance")
    else:
        stmt = stmt.order_by(Memory.updated_at.desc())

    stmt = stmt.limit(req.limit)
    result = await session.execute(stmt)
    
    if embedding:
        return [(_to_record(row.Memory), 1.0 - float(row.distance)) for row in result.all()]
    else:
        return [(_to_record(m), 1.0) for m in result.scalars().all()]


async def get_grounding_pack(
    session: AsyncSession,
    req: MemoryGetContextRequest
) -> MemoryGetContextResponse:
    """Synthesize a grounding pack for LLM context."""
    find_req = MemoryFindRequest(
        query=req.query,
        filters={"domain": req.domain} if req.domain else {},
        limit=req.max_items
    )
    hits = await find_memories_v1(session, find_req)
    
    records = []
    themes = set()
    risks = []
    
    for rec, score in hits:
        records.append({
            "id": rec.id,
            "title": rec.title,
            "entity_type": rec.entity_type,
            "excerpt": rec.content[:300] + "..." if len(rec.content) > 300 else rec.content,
            "relevance": score
        })
        for t in rec.tags: themes.add(t)
        if rec.entity_type.lower() == "risk":
            risks.append(rec.content)

    summary = f"OpenBrain found {len(records)} relevant memories for query: '{req.query}'."
    
    return MemoryGetContextResponse(
        query=req.query,
        summary=summary,
        records=records,
        themes=list(themes)[:10],
        risks=risks[:5]
    )
