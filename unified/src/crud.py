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
    MaintenanceReportDetail,
    MaintenanceReportEntry,
    MaintenanceRequest,
    MemoryCreate,
    MemoryFindRequest,
    MemoryGetContextRequest,
    MemoryGetContextResponse,
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
POLICY_VERSIONED_ENTITY_TYPES = {
    "decision",
    "policy",
    "risk",
    "incident",
    "incidentreport",
    "approval",
}

EXPORT_POLICY: dict[str, dict[str, Any]] = {
    "public": {
        "allow_fields": None,
        "redact_content": False,
        "allow_tags": True,
        "allow_match_key": True,
    },
    "internal": {
        "allow_fields": {
            "id",
            "tenant_id",
            "domain",
            "entity_type",
            "content",
            "owner",
            "status",
            "version",
            "sensitivity",
            "superseded_by",
            "tags",
            "relations",
            "obsidian_ref",
            "custom_fields",
            "content_hash",
            "match_key",
            "previous_id",
            "root_id",
            "valid_from",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        },
        "redact_content": True,
        "allow_tags": True,
        "allow_match_key": True,
    },
    "confidential": {
        "allow_fields": {
            "id",
            "tenant_id",
            "domain",
            "entity_type",
            "content",
            "owner",
            "status",
            "version",
            "sensitivity",
            "superseded_by",
            "tags",
            "relations",
            "obsidian_ref",
            "custom_fields",
            "content_hash",
            "match_key",
            "previous_id",
            "root_id",
            "valid_from",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        },
        "redact_content": True,
        "allow_tags": False,
        "allow_match_key": False,
    },
    "restricted": {
        "allow_fields": {
            "id",
            "tenant_id",
            "domain",
            "entity_type",
            "content",
            "owner",
            "status",
            "version",
            "sensitivity",
            "superseded_by",
            "tags",
            "relations",
            "obsidian_ref",
            "custom_fields",
            "content_hash",
            "match_key",
            "previous_id",
            "root_id",
            "valid_from",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        },
        "redact_content": True,
        "allow_tags": False,
        "allow_match_key": False,
    },
}


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
        tenant_id=meta.get("tenant_id"),
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
        custom_fields=meta.get("custom_fields") or {},
        content_hash=m.content_hash,
        version=m.version,
        previous_id=meta.get("previous_id"),
        root_id=meta.get("root_id"),
        superseded_by=m.superseded_by,
        valid_from=m.valid_from,
        created_at=m.created_at,
        updated_at=m.updated_at,
        created_by=m.created_by,
        updated_by=meta.get("updated_by") or m.created_by,
    )

def _to_out(m: Memory) -> MemoryOut:
    """Legacy helper for backward compatibility."""
    meta = m.metadata_ or {}
    return MemoryOut(
        id=m.id,
        tenant_id=meta.get("tenant_id"),
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
        custom_fields=meta.get("custom_fields") or {},
        content_hash=m.content_hash,
        match_key=m.match_key,
        previous_id=meta.get("previous_id"),
        root_id=meta.get("root_id"),
        valid_from=m.valid_from,
        created_at=m.created_at,
        updated_at=m.updated_at,
        created_by=m.created_by,
        updated_by=meta.get("updated_by") or m.created_by,
    )


def _normalize_entity_type(entity_type: str) -> str:
    return "".join(ch for ch in entity_type.lower() if ch.isalnum())


def _requires_append_only(domain: str | DomainEnum, entity_type: str) -> bool:
    domain_value = domain.value if isinstance(domain, DomainEnum) else domain
    return domain_value == "corporate" or _normalize_entity_type(entity_type) in POLICY_VERSIONED_ENTITY_TYPES


def _can_hard_delete(domain: str | DomainEnum, entity_type: str) -> bool:
    return not _requires_append_only(domain, entity_type)


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


def _export_record(record: dict[str, Any], sensitivity: str, role: str) -> dict[str, Any]:
    # Admin always receives the full record — no redaction.
    if role == "admin":
        return record

    # Non-admin callers (e.g. service accounts) follow sensitivity-based policy.
    policy = EXPORT_POLICY.get(sensitivity, EXPORT_POLICY["restricted"])
    exported = {field: record.get(field) for field in (policy["allow_fields"] or record.keys())}
    if policy["redact_content"]:
        exported["content"] = f"[REDACTED — {sensitivity} sensitivity]"
    exported["owner"] = "[REDACTED]"
    exported["relations"] = {}
    exported["obsidian_ref"] = None
    exported["custom_fields"] = {}
    exported["content_hash"] = ""
    exported["tenant_id"] = None
    if not policy["allow_tags"] or role == "internal":
        exported["tags"] = []
    if not policy["allow_match_key"]:
        exported["match_key"] = None
    return exported


# ---------------------------------------------------------------------------
# V1 UNIFIED ENGINE
# ---------------------------------------------------------------------------

async def handle_memory_write(
    session: AsyncSession,
    request: MemoryWriteRequest,
    actor: str = "agent",
    _commit: bool = True,
) -> MemoryWriteResponse:
    """The canonical write engine for OpenBrain.

    _commit controls whether the session is committed after each write.
    Set to False when the caller manages the transaction (e.g. atomic batch).
    """
    rec = request.record
    mode = request.write_mode
    domain = rec.domain
    append_only_policy = _requires_append_only(domain, rec.entity_type)
    
    # 1. Domain Governance Rules
    if domain == "corporate":
        # upsert is upgraded to append_version so that brain_store(domain="corporate")
        # works correctly via both the MCP gateway and legacy endpoints.
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
            return MemoryWriteResponse(status="failed", errors=["match_key is required for corporate domain — ensures idempotency on append-only records."])

    # 2. Match existing record — lock the row to prevent concurrent versioning/update
    # races on the same match_key.  The INSERT gap (two concurrent creates) is
    # prevented by the UNIQUE(match_key) DB constraint; without it this reduces
    # but does not eliminate races.
    existing = None
    if rec.match_key:
        stmt = (
            select(Memory)
            .where(Memory.match_key == rec.match_key, Memory.status == "active")
            .with_for_update()
        )
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

    # Guardrail: warn on match_key-less writes for non-corporate domains.
    # Corporate already enforces match_key above.  For build/personal the write
    # proceeds, but without a match_key there is no idempotency key and repeated
    # calls will silently accumulate duplicate records.
    if not rec.match_key and rec.domain != "corporate":
        log.warning(
            "duplicate_risk_write",
            domain=rec.domain,
            entity_type=rec.entity_type,
            owner=rec.owner,
            hint="Provide match_key for idempotent writes",
        )

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
                "tenant_id": rec.tenant_id,
                "custom_fields": rec.custom_fields,
                "updated_by": actor,
                "source": rec.source.model_dump(),
                "governance": {
                    "mutable": not append_only_policy,
                    "append_only": append_only_policy
                }
            }
        )
        session.add(memory)
        await session.flush()
        memory.metadata_ = {
            **(memory.metadata_ or {}),
            "previous_id": None,
            "root_id": memory.id,
        }
        
        if domain == "corporate":
            await _audit(session, "create", memory.id, actor=actor, tool_name="memory.write")

        if _commit:
            await session.commit()
            await session.refresh(memory)
        else:
            await session.flush()
        return MemoryWriteResponse(status="created", record=_to_record(memory))

    else:
        # --- UPDATE or VERSION ---
        # Skip if content and key metadata are unchanged — applies to both upsert
        # (build/personal) and append_version (corporate).  For corporate this prevents
        # a new audit version being created on every idempotent brain_store call.
        if existing.content_hash == content_hash:
            changed = (
                existing.owner != rec.owner
                or existing.tags != rec.tags
                or existing.obsidian_ref != rec.obsidian_ref
                or existing.sensitivity != rec.sensitivity
            )
            if not changed:
                return MemoryWriteResponse(status="skipped", record=_to_record(existing))

        if mode == WriteMode.append_version or append_only_policy:
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
                    "tenant_id": rec.tenant_id or existing.metadata_.get("tenant_id"),
                    "custom_fields": rec.custom_fields or existing.metadata_.get("custom_fields", {}),
                    "updated_by": actor,
                    "previous_id": existing.id,
                    "root_id": existing.metadata_.get("root_id") or existing.id,
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

            if _commit:
                await session.commit()
                await session.refresh(new_memory)
            else:
                await session.flush()
            return MemoryWriteResponse(status="versioned", record=_to_record(new_memory))
        else:
            # --- MUTATE IN PLACE (build/personal) ---
            # Fetch embedding BEFORE mutating fields — if Ollama fails, no partial write.
            new_embedding = await get_embedding(rec.content)
            existing.content = rec.content
            existing.content_hash = content_hash
            existing.embedding = new_embedding
            existing.owner = rec.owner
            existing.tags = rec.tags
            existing.relations = rec.relations.model_dump()
            existing.obsidian_ref = rec.obsidian_ref
            existing.entity_type = rec.entity_type
            existing.sensitivity = rec.sensitivity
            
            # Assign a new dict so SQLAlchemy detects the JSONB column as dirty.
            # Mutating existing.metadata_ in-place is NOT tracked without MutableDict.
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
    results = []
    summary = {"received": len(request.records), "created": 0, "updated": 0, "versioned": 0, "skipped": 0, "failed": 0}

    # Atomic mode: all writes share one transaction — any failure rolls back everything.
    # Non-atomic (default): each write is committed independently; partial success is allowed.
    atomic = request.atomic

    async def _process_records(commit_each: bool) -> None:
        for i, rec in enumerate(request.records):
            try:
                existing_id = None
                if rec.match_key:
                    existing_stmt = select(Memory.id).where(Memory.match_key == rec.match_key, Memory.status == "active")
                    existing_res = await session.execute(existing_stmt)
                    existing_id = existing_res.scalar_one_or_none()

                res = await handle_memory_write(
                    session,
                    MemoryWriteRequest(record=rec, write_mode=request.write_mode),
                    actor=actor,
                    _commit=commit_each,
                )
                results.append(BatchResultItem(
                    input_index=i,
                    status=res.status,
                    record_id=res.record.id if res.record else None,
                    previous_record_id=existing_id if res.status in {"updated", "versioned", "skipped"} else None,
                    match_key=rec.match_key,
                    warnings=res.warnings,
                    error=res.errors[0] if res.errors else None,
                ))
                summary[res.status] = summary.get(res.status, 0) + 1
            except Exception as e:
                results.append(BatchResultItem(
                    input_index=i, status="failed",
                    match_key=rec.match_key, error=str(e),
                ))
                summary["failed"] += 1
                if atomic:
                    raise  # abort the whole batch
                else:
                    # Roll back any partial mutations so the session stays valid
                    # for subsequent records.
                    await session.rollback()

    if atomic:
        try:
            await _process_records(commit_each=False)
            await session.commit()  # single commit for the entire batch
        except Exception:
            await session.rollback()
            overall = "failed"
            return MemoryWriteManyResponse(status=overall, summary=summary, results=results)
    else:
        await _process_records(commit_each=True)

    overall = "success" if summary["failed"] == 0 else ("partial_success" if summary["failed"] < len(request.records) else "failed")
    return MemoryWriteManyResponse(status=overall, summary=summary, results=results)


# ---------------------------------------------------------------------------
# Legacy compatibility (Stay available for now)
# ---------------------------------------------------------------------------

async def store_memory(session: AsyncSession, data: MemoryCreate, actor: str = "agent") -> MemoryOut:
    """Deprecated: using v1 handle_memory_write internally."""
    write_rec = MemoryWriteRecord(
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
    res = await handle_memory_write(
        session,
        MemoryWriteRequest(record=write_rec, write_mode=WriteMode.upsert),
        actor=actor,
    )
    if res.status == "failed":
        raise ValueError(f"Write failed: {res.errors}")
    return _to_out(await get_memory_raw(session, res.record.id))

async def get_memory_raw(session: AsyncSession, memory_id: str) -> Memory:
    stmt = select(Memory).where(Memory.id == memory_id)
    res = await session.execute(stmt)
    return res.scalar_one()

async def store_memories_bulk(session: AsyncSession, items: list[MemoryCreate]) -> list[MemoryOut]:
    recs = [
        MemoryWriteRecord(
            content=i.content,
            domain=i.domain,
            entity_type=i.entity_type,
            owner=i.owner,
            tenant_id=i.tenant_id,
            tags=i.tags,
            match_key=i.match_key,
            obsidian_ref=i.obsidian_ref,
            sensitivity=i.sensitivity,
            custom_fields=i.custom_fields,
            relations=MemoryRelations(**(i.relations or {})),
        )
        for i in items
    ]
    res = await handle_memory_write_many(session, MemoryWriteManyRequest(records=recs, write_mode=WriteMode.upsert))
    # Batch fetch all written records in a single query (avoids N+1).
    ids = [r.record_id for r in res.results if r.record_id]
    if not ids:
        return []
    stmt = select(Memory).where(Memory.id.in_(ids))
    result = await session.execute(stmt)
    id_to_mem = {m.id: _to_out(m) for m in result.scalars().all()}
    return [id_to_mem[r.record_id] for r in res.results if r.record_id and r.record_id in id_to_mem]

async def get_memory(session: AsyncSession, memory_id: str) -> MemoryOut | None:
    stmt = select(Memory).where(Memory.id == memory_id)
    result = await session.execute(stmt)
    m = result.scalar_one_or_none()
    return _to_out(m) if m else None


async def get_memory_as_record(
    session: AsyncSession, memory_id: str
) -> tuple[MemoryRecord | None, MemoryOut | None]:
    """Return both canonical MemoryRecord and legacy MemoryOut from a single DB fetch.

    Used by the V1 GET endpoint so that access-control helpers (which accept MemoryOut)
    and the V1 response (MemoryRecord) share one database round-trip.
    """
    stmt = select(Memory).where(Memory.id == memory_id)
    result = await session.execute(stmt)
    m = result.scalar_one_or_none()
    if m is None:
        return None, None
    return _to_record(m), _to_out(m)

async def list_memories(session: AsyncSession, filters: dict[str, Any], limit: int = 20) -> list[MemoryOut]:
    stmt = select(Memory)
    if "domain" in filters:
        domains = filters["domain"] if isinstance(filters["domain"], list) else [filters["domain"]]
        stmt = stmt.where(Memory.domain.in_([DomainEnum(domain) for domain in domains]))
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
    if "tenant_id" in filters:
        stmt = stmt.where(Memory.metadata_["tenant_id"].astext == filters["tenant_id"])

    stmt = stmt.order_by(Memory.updated_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return [_to_out(m) for m in result.scalars().all()]

async def search_memories(session: AsyncSession, req: SearchRequest) -> list[tuple[MemoryOut, float]]:
    embedding = await get_embedding(req.query)
    stmt = select(Memory, Memory.embedding.cosine_distance(embedding).label("distance")).where(Memory.status == "active")
    filters = req.filters
    if "domain" in filters:
        domains = filters["domain"] if isinstance(filters["domain"], list) else [filters["domain"]]
        stmt = stmt.where(Memory.domain.in_([DomainEnum(domain) for domain in domains]))
    if "entity_type" in filters:
        stmt = stmt.where(Memory.entity_type == filters["entity_type"])
    if "sensitivity" in filters:
        stmt = stmt.where(Memory.sensitivity == filters["sensitivity"])
    if "tenant_id" in filters:
        stmt = stmt.where(Memory.metadata_["tenant_id"].astext == filters["tenant_id"])
    if "owner" in filters:
        stmt = stmt.where(Memory.owner == filters["owner"])
    stmt = stmt.order_by("distance").limit(req.top_k)
    result = await session.execute(stmt)
    return [(_to_out(row.Memory), 1.0 - float(row.distance)) for row in result.all()]

async def update_memory(session: AsyncSession, memory_id: str, data: MemoryUpdate, actor: str = "agent") -> MemoryOut | None:
    stmt = select(Memory).where(Memory.id == memory_id)
    res = await session.execute(stmt)
    m = res.scalar_one_or_none()
    if not m: return None

    metadata = m.metadata_ or {}
    write_rec = MemoryWriteRecord(
        match_key=m.match_key,
        content=data.content,
        domain=m.domain.value,
        entity_type=m.entity_type,
        title=data.title if data.title is not None else metadata.get("title"),
        owner=data.owner if data.owner is not None else m.owner,
        tenant_id=data.tenant_id if data.tenant_id is not None else metadata.get("tenant_id"),
        tags=data.tags if data.tags is not None else m.tags,
        relations=MemoryRelations(**(data.relations if data.relations is not None else (m.relations or {}))),
        obsidian_ref=data.obsidian_ref if data.obsidian_ref is not None else m.obsidian_ref,
        sensitivity=data.sensitivity if data.sensitivity else m.sensitivity,
        custom_fields=data.custom_fields if data.custom_fields is not None else (metadata.get("custom_fields") or {}),
    )
    write_mode = WriteMode.append_version if _requires_append_only(m.domain, m.entity_type) else WriteMode.upsert
    res_v1 = await handle_memory_write(
        session,
        MemoryWriteRequest(record=write_rec, write_mode=write_mode),
        actor=actor,
    )
    if res_v1.status == "failed":
        raise ValueError(f"Update failed: {'; '.join(res_v1.errors)}")
    if res_v1.record:
        return await get_memory(session, res_v1.record.id)
    return None

async def delete_memory(session: AsyncSession, memory_id: str, actor: str = "agent") -> bool:
    stmt = select(Memory).where(Memory.id == memory_id)
    result = await session.execute(stmt)
    m = result.scalar_one_or_none()
    if m is None: return False
    if not _can_hard_delete(m.domain, m.entity_type):
        raise ValueError("Cannot hard-delete append-only memories.")
    await _audit(
        session,
        "delete",
        m.id,
        actor=actor,
        tool_name="memory.delete",
        meta={
            "domain": m.domain.value if isinstance(m.domain, DomainEnum) else m.domain,
            "entity_type": m.entity_type,
            "owner": m.owner,
            "tenant_id": (m.metadata_ or {}).get("tenant_id"),
            "version": m.version,
        },
    )
    await session.delete(m)
    await session.commit()
    return True

async def upsert_memories_bulk(session: AsyncSession, items: list[MemoryUpsertItem]) -> BulkUpsertResult:
    missing_match_keys = [str(index) for index, item in enumerate(items) if not item.match_key]
    if missing_match_keys:
        raise ValueError(
            "bulk-upsert requires match_key for every record; missing at indexes: "
            + ", ".join(missing_match_keys)
        )
    recs = [
        MemoryWriteRecord(
            content=i.content,
            domain=i.domain,
            entity_type=i.entity_type,
            owner=i.owner,
            tenant_id=i.tenant_id,
            tags=i.tags,
            match_key=i.match_key,
            obsidian_ref=i.obsidian_ref,
            sensitivity=i.sensitivity,
            custom_fields=i.custom_fields,
        )
        for i in items
    ]
    res = await handle_memory_write_many(session, MemoryWriteManyRequest(records=recs, write_mode=WriteMode.upsert))

    # Batch fetch all touched records in a single query (avoids N+1).
    # "versioned" is included because corporate domain upgrades upsert → append_version,
    # producing "versioned" status rather than "updated".
    ids = [r.record_id for r in res.results if r.record_id and r.status in {"created", "updated", "versioned"}]
    if ids:
        stmt = select(Memory).where(Memory.id.in_(ids))
        result = await session.execute(stmt)
        id_to_mem = {m.id: _to_out(m) for m in result.scalars().all()}
    else:
        id_to_mem = {}

    inserted, updated, skipped = [], [], []
    for r in res.results:
        m = id_to_mem.get(r.record_id) if r.record_id else None
        if r.status == "created" and m:
            inserted.append(m)
        elif r.status in {"updated", "versioned"} and m:
            # "versioned" (corporate append-only) is reported as "updated" in BulkUpsertResult.
            updated.append(m)
        elif r.status == "skipped":
            skipped.append(r.record_id or "")
    return BulkUpsertResult(inserted=inserted, updated=updated, skipped=skipped)

async def export_memories(session: AsyncSession, ids: list[str], role: str = "service") -> list[dict]:
    stmt = select(Memory).where(Memory.id.in_(ids))
    result = await session.execute(stmt)
    memories = result.scalars().all()
    exported = []
    for m in memories:
        out = _to_out(m).model_dump(mode="json")
        exported.append(_export_record(out, m.sensitivity, role))
    return exported

async def sync_check(
    session: AsyncSession,
    *,
    memory_id: str | None = None,
    match_key: str | None = None,
    obsidian_ref: str | None = None,
    file_hash: str | None = None,
) -> dict[str, str | None]:
    # Defensive guard: schema validator should catch this, but protect at the
    # function level too so direct callers (e.g. tests) get a clean error.
    if memory_id is None and match_key is None and obsidian_ref is None:
        raise ValueError("Exactly one of memory_id, match_key, or obsidian_ref must be provided.")

    stmt = select(Memory).where(Memory.status == "active")
    if memory_id is not None:
        stmt = stmt.where(Memory.id == memory_id)
    elif match_key is not None:
        stmt = stmt.where(Memory.match_key == match_key).order_by(Memory.updated_at.desc()).limit(1)
    else:
        stmt = stmt.where(Memory.obsidian_ref == obsidian_ref).order_by(Memory.updated_at.desc()).limit(1)

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
        response.update({"status": "outdated", "message": "Hash mismatch. Update required."})
        return response
    response.update({"status": "synced", "message": "Memory is up to date."})
    return response

async def run_maintenance(session: AsyncSession, req: MaintenanceRequest, actor: str = "agent") -> MaintenanceReport:
    actions: list[MaintenanceAction] = []
    dedup_count, owners_norm, links_fixed = 0, 0, 0

    # Count total active memories without loading them all into Python.
    total_result = await session.execute(
        select(func.count(Memory.id)).where(Memory.status == "active")
    )
    total = total_result.scalar_one()

    # --- DEDUPLICATION (SQL GROUP BY — avoids O(n²) full table scan) ---
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
                .order_by(Memory.created_at.asc())  # keep oldest as canonical
            )
            members = (await session.execute(members_stmt)).scalars().all()
            canonical = members[0]
            for dup in members[1:]:
                dedup_count += 1
                actions.append(MaintenanceAction(action="dedup", memory_id=dup.id, detail=f"Exact duplicate of {canonical.id}"))
                if not req.dry_run:
                    if _requires_append_only(dup.domain, dup.entity_type):
                        if req.allow_exact_dedup_override:
                            # Governance-safe override for exact duplicates:
                            # canonical record is preserved and stays active;
                            # only the duplicate is superseded — no content is
                            # changed or physically deleted.
                            dup.status = "superseded"
                            dup.superseded_by = canonical.id
                            actions.append(MaintenanceAction(
                                action="dedup_override",
                                memory_id=dup.id,
                                detail=f"Exact duplicate of {canonical.id} superseded via governance override (append-only)",
                            ))
                        else:
                            actions.append(MaintenanceAction(
                                action="policy_skip",
                                memory_id=dup.id,
                                detail="Skipped dedup mutation for append-only memory",
                            ))
                    else:
                        dup.status = "superseded"
                        dup.superseded_by = canonical.id

    # --- OWNER NORMALIZATION (targeted query — only loads affected records) ---
    if req.normalize_owners:
        old_owners = list(req.normalize_owners.keys())
        norm_stmt = select(Memory).where(Memory.status == "active", Memory.owner.in_(old_owners))
        norm_memories = (await session.execute(norm_stmt)).scalars().all()
        for m in norm_memories:
            new_owner = req.normalize_owners[m.owner]
            actions.append(MaintenanceAction(action="normalize_owner", memory_id=m.id, detail=f"'{m.owner}' -> '{new_owner}'"))
            if not req.dry_run:
                if _requires_append_only(m.domain, m.entity_type):
                    actions.append(MaintenanceAction(
                        action="policy_skip",
                        memory_id=m.id,
                        detail="Skipped owner normalization for append-only memory",
                    ))
                    continue
                m.owner = new_owner
                owners_norm += 1

    # --- SUPERSEDED LINK REPAIR ---
    if req.fix_superseded_links:
        active_ids_result = await session.execute(select(Memory.id).where(Memory.status == "active"))
        active_ids = {row[0] for row in active_ids_result.all()}

        superseded_stmt = select(Memory).where(Memory.superseded_by.isnot(None), Memory.status == "superseded")
        superseded_memories = (await session.execute(superseded_stmt)).scalars().all()
        for m in superseded_memories:
            if m.superseded_by and m.superseded_by not in active_ids:
                links_fixed += 1
                actions.append(MaintenanceAction(action="fix_link", memory_id=m.id, detail=f"superseded_by {m.superseded_by} not found in active"))
                if not req.dry_run:
                    if _requires_append_only(m.domain, m.entity_type):
                        actions.append(MaintenanceAction(
                            action="policy_skip",
                            memory_id=m.id,
                            detail="Skipped supersession link repair for append-only memory",
                        ))
                        continue
                    m.superseded_by, m.status = None, "active"

    report = MaintenanceReport(
        dry_run=req.dry_run,
        actions=actions,
        total_scanned=total,
        dedup_found=dedup_count,
        owners_normalized=owners_norm,
        links_fixed=links_fixed,
    )

    if req.dry_run:
        # Skip persisting the audit entry for dry runs — they must not pollute reports.
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
    session.add(audit_entry)
    await session.flush()
    report.report_id = audit_entry.id

    await session.commit()
    return report


async def get_memory_status_counts(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        select(Memory.status, func.count(Memory.id)).group_by(Memory.status)
    )
    counts = {status: count for status, count in result.all()}
    return {
        "active": int(counts.get("active", 0)),
        "superseded": int(counts.get("superseded", 0)),
        "archived": int(counts.get("archived", 0)),
        "deleted": int(counts.get("deleted", 0)),
    }


async def get_memory_domain_status_counts(session: AsyncSession) -> dict[str, dict[str, int]]:
    result = await session.execute(
        select(Memory.domain, Memory.status, func.count(Memory.id)).group_by(Memory.domain, Memory.status)
    )
    counts: dict[str, dict[str, int]] = {
        "corporate": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
        "build": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
        "personal": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
    }
    for domain, status, count in result.all():
        domain_key = domain.value if isinstance(domain, DomainEnum) else str(domain)
        if domain_key not in counts:
            counts[domain_key] = {"active": 0, "superseded": 0, "archived": 0, "deleted": 0}
        counts[domain_key][str(status)] = int(count)
    return counts


async def list_maintenance_reports(session: AsyncSession, limit: int = 20) -> list[MaintenanceReportEntry]:
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.operation == "maintain", AuditLog.tool_name == "memory.maintain")
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


async def get_maintenance_report(session: AsyncSession, report_id: str) -> MaintenanceReportDetail | None:
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
    if "tenant_id" in filters:
        tenant_ids = filters["tenant_id"] if isinstance(filters["tenant_id"], list) else [filters["tenant_id"]]
        stmt = stmt.where(Memory.metadata_["tenant_id"].astext.in_(tenant_ids))
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
    req: MemoryGetContextRequest,
    owner: str | None = None,
    tenant_id: str | None = None,
) -> MemoryGetContextResponse:
    """Synthesize a grounding pack for LLM context."""
    find_req = MemoryFindRequest(
        query=req.query,
        filters={"domain": req.domain} if req.domain else {},
        limit=req.max_items
    )
    if owner:
        find_req.filters["owner"] = owner
    if tenant_id:
        find_req.filters["tenant_id"] = tenant_id
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
