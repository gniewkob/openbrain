from __future__ import annotations

from inspect import isawaitable
from typing import Any

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog, DomainEnum, Memory
from .schemas import (
    GovernanceMetadata,
    MemoryOut,
    MemoryRecord,
    MemoryRelations,
    SourceMetadata,
)

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

CORPORATE = DomainEnum.corporate
STATUS_ACTIVE = "active"
STATUS_SUPERSEDED = "superseded"
STATUS_DUPLICATE = "duplicate"


def _resolve_created_by(memory: Memory) -> str:
    created_by = getattr(memory, "created_by", None)
    if isinstance(created_by, str) and created_by.strip():
        return created_by.strip()
    return "agent"


def _resolve_updated_by(memory: Memory) -> str:
    meta = memory.metadata_ or {}
    candidate = meta.get("updated_by")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return _resolve_created_by(memory)


def _to_record(m: Memory) -> MemoryRecord:
    meta = m.metadata_ or {}
    source = meta.get("source", {})
    gov = meta.get("governance", {})
    tenant_id = m.tenant_id or meta.get("tenant_id")
    return MemoryRecord(
        id=m.id,
        match_key=m.match_key,
        tenant_id=tenant_id,
        domain=m.domain.value if isinstance(m.domain, DomainEnum) else m.domain,
        entity_type=m.entity_type,
        title=meta.get("title") or m.entity_type,
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
        created_by=_resolve_created_by(m),
        updated_by=_resolve_updated_by(m),
    )


def _to_out(m: Memory) -> MemoryOut:
    meta = m.metadata_ or {}
    tenant_id = m.tenant_id or meta.get("tenant_id")
    return MemoryOut(
        id=m.id,
        tenant_id=tenant_id,
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
        created_by=_resolve_created_by(m),
        updated_by=_resolve_updated_by(m),
    )


def _requires_append_only(domain: str | DomainEnum, entity_type: str) -> bool:
    del entity_type
    domain_value = domain.value if isinstance(domain, DomainEnum) else domain
    return domain_value == "corporate"


def _can_hard_delete(domain: str | DomainEnum, entity_type: str) -> bool:
    return not _requires_append_only(domain, entity_type)


async def _audit(
    session: AsyncSession,
    operation: str,
    memory_id: str | None,
    actor: str = "agent",
    tool_name: str = "",
    meta: dict | None = None,
    actor_ip: str | None = None,
    request_id: str | None = None,
    authorization_context: str | None = None,
) -> None:
    entry = AuditLog(
        operation=operation,
        tool_name=tool_name,
        memory_id=memory_id,
        actor=actor,
        actor_ip=actor_ip,
        request_id=request_id,
        authorization_context=authorization_context,
        meta=meta or {},
    )
    maybe_result = session.add(entry)
    if isawaitable(maybe_result):
        await maybe_result


def _export_record(
    record: dict[str, Any], sensitivity: str, role: str
) -> dict[str, Any]:
    if role == "admin":
        return record
    policy = EXPORT_POLICY.get(sensitivity, EXPORT_POLICY["restricted"])
    exported = {
        field: record.get(field) for field in (policy["allow_fields"] or record.keys())
    }
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


def _tenant_filter_expr(tenant_ids: list[str]):
    return or_(
        Memory.tenant_id.in_(tenant_ids),
        Memory.metadata_["tenant_id"].astext.in_(tenant_ids),
    )


def _record_matches_existing(existing: Memory, rec, content_hash: str) -> bool:
    metadata = existing.metadata_ or {}
    return (
        existing.content_hash == content_hash
        and existing.owner == rec.owner
        and (existing.tenant_id or metadata.get("tenant_id")) == rec.tenant_id
        and existing.tags == rec.tags
        and (existing.relations or {}) == rec.relations.model_dump()
        and existing.obsidian_ref == rec.obsidian_ref
        and existing.entity_type == rec.entity_type
        and existing.sensitivity == rec.sensitivity
        and metadata.get("title") == rec.title
        and (metadata.get("custom_fields") or {}) == rec.custom_fields
        and (metadata.get("source") or {}) == rec.source.model_dump()
    )
