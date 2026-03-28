"""
OpenBrain Unified v2.1 — Canonical Schemas.

Implements the Memory Platform V1 contract:
- Unified MemoryRecord model
- Explicit WriteModes
- Tiered response envelopes
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class WriteMode(str, Enum):
    create_only = "create_only"      # Fail if match_key exists
    update_only = "update_only"      # Fail if ID/match_key missing
    upsert = "upsert"                # Create or update in-place
    append_version = "append_version" # Create new version, supersede old


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class SourceMetadata(BaseModel):
    type: Literal["manual", "agent", "sync", "import", "api"] = "agent"
    system: Literal["chatgpt", "obsidian", "notion", "slack", "github", "other"] = "chatgpt"
    reference: Optional[str] = None


class GovernanceMetadata(BaseModel):
    mutable: bool = True
    append_only: bool = False
    retention_class: Literal["default", "audit", "temporary"] = "default"


class MemoryRelations(BaseModel):
    parent: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Canonical Resource Model
# ---------------------------------------------------------------------------

class MemoryRecord(BaseModel):
    id: str
    match_key: Optional[str] = None
    tenant_id: Optional[str] = None
    domain: Literal["corporate", "build", "personal"]
    entity_type: str
    title: Optional[str] = None
    content: str
    summary: Optional[str] = None
    owner: str
    tags: list[str] = Field(default_factory=list)
    relations: MemoryRelations = Field(default_factory=MemoryRelations)
    status: Literal["active", "archived", "superseded", "deleted"] = "active"
    sensitivity: Literal["public", "internal", "confidential", "restricted"] = "internal"
    source: SourceMetadata = Field(default_factory=SourceMetadata)
    governance: GovernanceMetadata = Field(default_factory=GovernanceMetadata)
    obsidian_ref: Optional[str] = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    content_hash: str
    version: int = 1
    previous_id: Optional[str] = None
    root_id: Optional[str] = None
    superseded_by: Optional[str] = None
    valid_from: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Request Models (V1)
# ---------------------------------------------------------------------------

class MemoryWriteRecord(BaseModel):
    """The data part of a write request."""
    match_key: Optional[str] = None
    tenant_id: Optional[str] = None
    domain: Literal["corporate", "build", "personal"]
    entity_type: str = "Note"
    title: Optional[str] = None
    content: str
    owner: str = ""
    tags: list[str] = Field(default_factory=list)
    relations: MemoryRelations = Field(default_factory=MemoryRelations)
    sensitivity: Literal["public", "internal", "confidential", "restricted"] = "internal"
    source: SourceMetadata = Field(default_factory=SourceMetadata)
    obsidian_ref: Optional[str] = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class MemoryWriteRequest(BaseModel):
    record: MemoryWriteRecord
    write_mode: WriteMode = WriteMode.upsert
    idempotency_key: Optional[str] = None


class MemoryWriteManyRequest(BaseModel):
    records: list[MemoryWriteRecord]
    write_mode: WriteMode = WriteMode.upsert
    atomic: bool = False


class MemoryFindRequest(BaseModel):
    query: Optional[str] = None
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = 10
    sort: Literal["relevance", "updated_at_desc"] = "relevance"


class MemoryGetContextRequest(BaseModel):
    query: str
    domain: Optional[str] = None
    max_items: int = 10
    output_mode: Literal["grounding_pack", "raw"] = "grounding_pack"


class ObsidianReadRequest(BaseModel):
    vault: str = "Documents"
    path: str


class ObsidianNoteResponse(BaseModel):
    vault: str
    path: str
    title: str
    content: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    file_hash: str


class ObsidianSyncRequest(BaseModel):
    vault: str = "Documents"
    paths: list[str] = Field(default_factory=list)
    folder: Optional[str] = None
    limit: int = 50
    domain: Literal["corporate", "build", "personal"] = "build"
    entity_type: str = "Architecture"
    owner: str = ""
    tags: list[str] = Field(default_factory=list)


class ObsidianSyncResponse(BaseModel):
    vault: str
    resolved_paths: list[str] = Field(default_factory=list)
    scanned: int
    summary: dict[str, int]
    results: list["BatchResultItem"] = Field(default_factory=list)


class SyncCheckRequest(BaseModel):
    memory_id: Optional[str] = None
    match_key: Optional[str] = None
    obsidian_ref: Optional[str] = None
    file_hash: Optional[str] = None

    @model_validator(mode="after")
    def validate_identifier_count(self) -> "SyncCheckRequest":
        identifiers = [self.memory_id, self.match_key, self.obsidian_ref]
        provided = [value for value in identifiers if value]
        if len(provided) != 1:
            raise ValueError("Exactly one of memory_id, match_key, or obsidian_ref must be provided.")
        return self


class SyncCheckResponse(BaseModel):
    status: Literal["synced", "outdated", "missing", "exists"]
    message: str
    memory_id: Optional[str] = None
    match_key: Optional[str] = None
    obsidian_ref: Optional[str] = None
    stored_hash: Optional[str] = None
    provided_hash: Optional[str] = None


# ---------------------------------------------------------------------------
# Response Envelopes (V1)
# ---------------------------------------------------------------------------

class MemoryWriteResponse(BaseModel):
    status: Literal["created", "updated", "versioned", "skipped", "failed"]
    record: Optional[MemoryRecord] = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BatchResultItem(BaseModel):
    input_index: int
    status: str
    operation_type: Optional[Literal["created", "updated", "versioned", "skipped", "failed"]] = None
    record_id: Optional[str] = None
    previous_record_id: Optional[str] = None
    match_key: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class MemoryWriteManyResponse(BaseModel):
    status: Literal["success", "partial_success", "failed"]
    summary: dict[str, int]
    results: list[BatchResultItem]
    errors: list[str] = Field(default_factory=list)


class MemoryGetContextResponse(BaseModel):
    query: str
    summary: str
    records: list[dict[str, Any]]
    themes: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Legacy compatibility (Deprecated)
# ---------------------------------------------------------------------------

class MemoryCreate(BaseModel):
    content: str
    domain: Literal["corporate", "build", "personal"] = "corporate"
    entity_type: str = "Decision"
    sensitivity: str = "internal"
    owner: str = ""
    created_by: str = "agent"
    tags: list[str] = Field(default_factory=list)
    relations: dict[str, Any] = Field(default_factory=dict)
    obsidian_ref: str | None = None
    match_key: str | None = None
    tenant_id: str | None = None
    status: Literal["active", "draft", "deprecated"] = "active"
    valid_from: Optional[datetime] = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class MemoryUpdate(BaseModel):
    content: str
    title: Optional[str] = None
    updated_by: str = "agent"
    sensitivity: Optional[str] = None
    owner: Optional[str] = None
    tags: Optional[list[str]] = None
    relations: Optional[dict[str, Any]] = None
    obsidian_ref: Optional[str] = None
    tenant_id: Optional[str] = None
    custom_fields: Optional[dict[str, Any]] = None


class MemoryUpsertItem(BaseModel):
    content: str
    domain: Literal["corporate", "build", "personal"] = "corporate"
    entity_type: str = "Decision"
    sensitivity: str = "internal"
    owner: str = ""
    created_by: str = "agent"
    tags: list[str] = Field(default_factory=list)
    relations: dict[str, Any] = Field(default_factory=dict)
    obsidian_ref: str | None = None
    match_key: str | None = None
    tenant_id: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: dict[str, Any] = Field(default_factory=dict)


class ExportRequest(BaseModel):
    ids: list[str]
    format: Literal["jsonl"] = "jsonl"


class MaintenanceRequest(BaseModel):
    dry_run: bool = True
    dedup_threshold: float = 0.05
    normalize_owners: dict[str, str] = Field(default_factory=dict)
    retype_rules: list[dict[str, str]] = Field(default_factory=list)
    fix_superseded_links: bool = True


class MemoryOut(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    domain: str
    entity_type: str
    content: str
    owner: str
    status: str
    version: int
    sensitivity: str
    superseded_by: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    relations: dict[str, Any] = Field(default_factory=dict)
    obsidian_ref: Optional[str] = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""
    match_key: Optional[str] = None
    previous_id: Optional[str] = None
    root_id: Optional[str] = None
    valid_from: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str | None = None

    model_config = {"from_attributes": True}


class SearchResult(BaseModel):
    memory: MemoryOut
    score: float


class BulkUpsertResult(BaseModel):
    inserted: list[MemoryOut] = Field(default_factory=list)
    updated: list[MemoryOut] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


class MaintenanceAction(BaseModel):
    action: str
    memory_id: str
    detail: str


class MaintenanceReport(BaseModel):
    report_id: Optional[str] = None
    dry_run: bool
    actions: list[MaintenanceAction] = Field(default_factory=list)
    total_scanned: int = 0
    dedup_found: int = 0
    owners_normalized: int = 0
    links_fixed: int = 0


class MaintenanceReportEntry(BaseModel):
    report_id: str
    created_at: datetime
    actor: str
    dry_run: bool
    total_scanned: int = 0
    dedup_found: int = 0
    owners_normalized: int = 0
    links_fixed: int = 0
    action_count: int = 0


class MaintenanceReportDetail(BaseModel):
    report_id: str
    created_at: datetime
    actor: str
    dry_run: bool
    actions: list[MaintenanceAction] = Field(default_factory=list)
    total_scanned: int = 0
    dedup_found: int = 0
    owners_normalized: int = 0
    links_fixed: int = 0


class PolicyScopeEntry(BaseModel):
    allowed_domains: list[Literal["corporate", "build", "personal"]] = Field(default_factory=list)
    read_domains: list[Literal["corporate", "build", "personal"]] = Field(default_factory=list)
    write_domains: list[Literal["corporate", "build", "personal"]] = Field(default_factory=list)
    admin_domains: list[Literal["corporate", "build", "personal"]] = Field(default_factory=list)


class PolicyRegistry(BaseModel):
    tenants: dict[str, PolicyScopeEntry] = Field(default_factory=dict)
    subjects: dict[str, PolicyScopeEntry] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Error Models
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[dict[str, Any]] = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
