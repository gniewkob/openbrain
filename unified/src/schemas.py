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
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator
from src.runtime_limits import load_runtime_limits

MAX_ENTITY_TYPE_LEN = 64
MAX_TITLE_LEN = 256
MAX_CONTENT_LEN = 20_000
MAX_OWNER_LEN = 128
MAX_TENANT_ID_LEN = 128
MAX_TAG_LEN = 64
MAX_TAGS = 32
MAX_MATCH_KEY_LEN = 256
MAX_QUERY_LEN = 2_000
MAX_PATH_LEN = 1_024
MAX_FILTER_LIMIT = 50
MAX_CONTEXT_ITEMS = 20
_RUNTIME_LIMITS = load_runtime_limits()
MAX_SYNC_LIMIT = _RUNTIME_LIMITS["max_sync_limit"]
MAX_BULK_RECORDS = _RUNTIME_LIMITS["max_bulk_items"]
MAX_EXPORT_IDS = _RUNTIME_LIMITS["max_bulk_items"]
MAX_POLICY_REWRITES = 100
MAX_CUSTOM_FIELDS = 20
MAX_CUSTOM_KEY_LEN = 64
MAX_CUSTOM_VALUE_STR_LEN = 256
MAX_CUSTOM_FIELDS_BYTES = 5_120

EntityTypeStr = Annotated[str, Field(max_length=MAX_ENTITY_TYPE_LEN)]
TitleStr = Annotated[str, Field(max_length=MAX_TITLE_LEN)]
ContentStr = Annotated[str, Field(max_length=MAX_CONTENT_LEN)]
OwnerStr = Annotated[str, Field(max_length=MAX_OWNER_LEN)]
# tenant_id must be non-empty and contain only safe identifier characters
# (letters, digits, hyphens, underscores) to prevent path-traversal and
# injection risks when used as a filter or partition key.
TenantIdStr = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_TENANT_ID_LEN,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
]
TagStr = Annotated[str, Field(max_length=MAX_TAG_LEN)]
MatchKeyStr = Annotated[str, Field(max_length=MAX_MATCH_KEY_LEN)]
QueryStr = Annotated[str, Field(max_length=MAX_QUERY_LEN)]
PathStr = Annotated[str, Field(max_length=MAX_PATH_LEN)]


# ---------------------------------------------------------------------------
# Custom fields validation
# ---------------------------------------------------------------------------

_KEY_RE = __import__("re").compile(r"^[A-Za-z0-9_.-]+$")


def _validate_custom_fields(v: Any) -> dict[str, Any]:
    """Validate custom_fields: key pattern, value types, and total size."""
    import json

    if not isinstance(v, dict):
        raise ValueError("custom_fields must be a dict")
    if len(v) > MAX_CUSTOM_FIELDS:
        raise ValueError(
            f"custom_fields exceeds max {MAX_CUSTOM_FIELDS} keys, got {len(v)}"
        )
    for key, val in v.items():
        if not isinstance(key, str):
            raise ValueError(f"custom_fields key must be str, got {type(key).__name__}")
        if len(key) > MAX_CUSTOM_KEY_LEN:
            raise ValueError(
                f"custom_fields key '{key[:32]}…' exceeds {MAX_CUSTOM_KEY_LEN} chars"
            )
        if not _KEY_RE.match(key):
            raise ValueError(f"custom_fields key '{key}' must match ^[A-Za-z0-9_.-]+$")
        if val is not None and not isinstance(val, (str, int, float, bool)):
            raise ValueError(
                f"custom_fields['{key}'] type {type(val).__name__} not allowed"
                " (str | int | float | bool | None only)"
            )
        if isinstance(val, str) and len(val) > MAX_CUSTOM_VALUE_STR_LEN:
            raise ValueError(
                f"custom_fields['{key}'] value exceeds {MAX_CUSTOM_VALUE_STR_LEN} chars"
            )
    size = len(json.dumps(v, separators=(",", ":")).encode())
    if size > MAX_CUSTOM_FIELDS_BYTES:
        raise ValueError(
            f"custom_fields JSON exceeds {MAX_CUSTOM_FIELDS_BYTES} bytes, got {size}"
        )
    return v


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WriteMode(str, Enum):
    """Determines how a write operation behaves when a matching record exists."""

    create_only = "create_only"  # Fail if match_key exists
    update_only = "update_only"  # Fail if ID/match_key missing
    upsert = "upsert"  # Create or update in-place
    append_version = "append_version"  # Create new version, supersede old


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class SourceMetadata(BaseModel):
    """Origin metadata describing how and where a memory was created."""

    type: Literal["manual", "agent", "sync", "import", "api"] = "agent"
    system: Literal["chatgpt", "obsidian", "notion", "slack", "github", "other"] = (
        "chatgpt"
    )
    reference: Optional[PathStr] = None


class GovernanceMetadata(BaseModel):
    """Governance flags controlling mutability and retention of a memory record."""

    mutable: bool = True
    append_only: bool = False
    retention_class: Literal["default", "audit", "temporary"] = "default"


class MemoryRelations(BaseModel):
    """Graph edges linking a memory to related records by role."""

    parent: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Canonical Resource Model
# ---------------------------------------------------------------------------


class MemoryRecord(BaseModel):
    """Full canonical memory record as stored and returned by the platform."""

    id: str
    match_key: Optional[MatchKeyStr] = None
    tenant_id: Optional[TenantIdStr] = None
    domain: Literal["corporate", "build", "personal"]
    entity_type: EntityTypeStr
    title: Optional[TitleStr] = None
    content: ContentStr
    summary: Optional[Annotated[str, Field(max_length=MAX_QUERY_LEN)]] = None
    owner: OwnerStr
    tags: list[TagStr] = Field(default_factory=list, max_length=MAX_TAGS)
    relations: MemoryRelations = Field(default_factory=MemoryRelations)
    status: Literal["active", "archived", "superseded", "deleted", "duplicate"] = (
        "active"
    )
    sensitivity: Literal["public", "internal", "confidential", "restricted"] = (
        "internal"
    )
    source: SourceMetadata = Field(default_factory=SourceMetadata)
    governance: GovernanceMetadata = Field(default_factory=GovernanceMetadata)
    obsidian_ref: Optional[PathStr] = None
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

    @field_validator("custom_fields", mode="before")
    @classmethod
    def _check_custom_fields(cls, v: Any) -> Any:
        """Delegate to shared custom_fields validator."""
        return _validate_custom_fields(v) if v is not None else {}


# ---------------------------------------------------------------------------
# Request Models (V1)
# ---------------------------------------------------------------------------


class MemoryWriteRecord(BaseModel):
    """The data part of a write request."""

    match_key: Optional[MatchKeyStr] = None
    tenant_id: Optional[TenantIdStr] = None
    domain: Literal["corporate", "build", "personal"]
    entity_type: EntityTypeStr = Field(default="Note", max_length=MAX_ENTITY_TYPE_LEN)
    title: Optional[TitleStr] = None
    content: ContentStr
    owner: OwnerStr = ""
    tags: list[TagStr] = Field(default_factory=list, max_length=MAX_TAGS)
    relations: MemoryRelations = Field(default_factory=MemoryRelations)
    sensitivity: Literal["public", "internal", "confidential", "restricted"] = (
        "internal"
    )
    source: SourceMetadata = Field(default_factory=SourceMetadata)
    obsidian_ref: Optional[PathStr] = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("custom_fields", mode="before")
    @classmethod
    def _check_custom_fields(cls, v: Any) -> Any:
        """Delegate to shared custom_fields validator."""
        return _validate_custom_fields(v) if v is not None else {}


class MemoryWriteRequest(BaseModel):
    """Request to write a single memory record with a specified write mode."""

    record: MemoryWriteRecord
    write_mode: WriteMode = WriteMode.upsert
    idempotency_key: Optional[str] = None


class MemoryWriteManyRequest(BaseModel):
    """Request to write multiple memory records in a single batch operation."""

    records: list[MemoryWriteRecord] = Field(max_length=MAX_BULK_RECORDS)
    write_mode: WriteMode = WriteMode.upsert
    atomic: bool = False


class MemoryFindRequest(BaseModel):
    """Request to search or filter memories with optional semantic query and filters."""

    query: Optional[QueryStr] = None
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=10, ge=1, le=MAX_FILTER_LIMIT)
    offset: int = Field(default=0, ge=0, le=10_000)
    sort: Literal["relevance", "updated_at_desc"] = "relevance"


class MemoryGetContextRequest(BaseModel):
    """Request to retrieve a grounding context pack for a given query."""

    query: QueryStr
    domain: Optional[str] = None
    max_items: int = Field(default=10, ge=1, le=MAX_CONTEXT_ITEMS)
    output_mode: Literal["grounding_pack", "raw"] = "grounding_pack"


class ObsidianReadRequest(BaseModel):
    """Request to read a single note from an Obsidian vault."""

    vault: Annotated[str, Field(max_length=MAX_OWNER_LEN)] = "Documents"
    path: PathStr


class ObsidianNoteResponse(BaseModel):
    """Response containing the content and metadata of a read Obsidian note."""

    vault: Annotated[str, Field(max_length=MAX_OWNER_LEN)]
    path: PathStr
    title: TitleStr
    content: ContentStr
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    tags: list[TagStr] = Field(default_factory=list, max_length=MAX_TAGS)
    file_hash: str


class ObsidianSyncRequest(BaseModel):
    """Request to import Obsidian notes into OpenBrain as memories."""

    vault: Annotated[str, Field(max_length=MAX_OWNER_LEN)] = "Documents"
    paths: list[PathStr] = Field(default_factory=list, max_length=MAX_SYNC_LIMIT)
    folder: Optional[PathStr] = None
    limit: int = Field(default=50, ge=1, le=MAX_SYNC_LIMIT)
    domain: Literal["corporate", "build", "personal"] = "build"
    entity_type: EntityTypeStr = "Architecture"
    owner: OwnerStr = ""
    tags: list[TagStr] = Field(default_factory=list, max_length=MAX_TAGS)


class ObsidianSyncResponse(BaseModel):
    """Response summarizing the result of an Obsidian-to-OpenBrain sync operation."""

    vault: Annotated[str, Field(max_length=MAX_OWNER_LEN)]
    resolved_paths: list[PathStr] = Field(
        default_factory=list, max_length=MAX_SYNC_LIMIT
    )
    scanned: int
    summary: dict[str, int]
    results: list["BatchResultItem"] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Obsidian Export (OpenBrain → Obsidian)
# ---------------------------------------------------------------------------


class ObsidianWriteRequest(BaseModel):
    """Request to write a note to Obsidian vault."""

    vault: Annotated[str, Field(max_length=MAX_OWNER_LEN)] = "Documents"
    path: PathStr
    content: ContentStr
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    overwrite: bool = False


class ObsidianWriteResponse(BaseModel):
    """Response from writing a note to Obsidian."""

    vault: str
    path: str
    title: str
    content: str
    frontmatter: dict[str, Any]
    tags: list[str]
    file_hash: str
    created: bool  # True if new, False if updated


class ObsidianExportRequest(BaseModel):
    """Request to export memories to Obsidian notes."""

    vault: Annotated[str, Field(max_length=MAX_OWNER_LEN)] = "Documents"
    folder: PathStr = "OpenBrain Export"
    memory_ids: Optional[list[str]] = Field(default=None, max_length=MAX_EXPORT_IDS)
    query: Optional[QueryStr] = None
    domain: Optional[Literal["corporate", "build", "personal"]] = None
    max_items: int = Field(default=50, ge=1, le=MAX_SYNC_LIMIT)
    template: Optional[str] = None  # Optional custom template


class ObsidianExportItem(BaseModel):
    """Single exported item result."""

    memory_id: str
    path: str
    title: str
    created: bool  # True if new, False if updated


class ObsidianExportResponse(BaseModel):
    """Response from exporting memories to Obsidian."""

    vault: str
    folder: str
    exported_count: int
    exported: list[ObsidianExportItem]
    errors: list[dict[str, str]]  # Each has memory_id and error


class ObsidianCollectionRequest(BaseModel):
    """Request to create a collection (index note) from memories."""

    query: QueryStr
    collection_name: TitleStr
    vault: Annotated[str, Field(max_length=MAX_OWNER_LEN)] = "Documents"
    folder: PathStr = "Collections"
    domain: Optional[Literal["corporate", "build", "personal"]] = None
    max_items: int = Field(default=50, ge=1, le=MAX_SYNC_LIMIT)
    group_by: Optional[Literal["entity_type", "owner", "tags"]] = None


class ObsidianCollectionResponse(BaseModel):
    """Response from creating a collection."""

    collection_name: str
    vault: str
    folder: str
    index_path: str
    exported_count: int
    exported: list[ObsidianExportItem]
    errors: list[dict[str, str]]


# ---------------------------------------------------------------------------
# Bidirectional Sync (OpenBrain ↔ Obsidian)
# ---------------------------------------------------------------------------


class ObsidianBidirectionalSyncRequest(BaseModel):
    """Request for bidirectional sync."""

    vault: Annotated[str, Field(max_length=MAX_OWNER_LEN)] = "Memory"
    strategy: Literal["last_write_wins", "domain_based", "manual_review"] = (
        "domain_based"
    )
    dry_run: bool = False  # If True, only detect changes without applying
    since: Optional[datetime] = None  # Only sync changes since this time


class ObsidianSyncChange(BaseModel):
    """Single detected change in bidirectional sync."""

    memory_id: str
    obsidian_path: str
    change_type: Literal["created", "updated", "deleted", "unchanged"]
    source: Literal["openbrain", "obsidian", "both"]
    conflict: bool = False
    resolution: Optional[str] = None


class ObsidianBidirectionalSyncResponse(BaseModel):
    """Response from bidirectional sync."""

    started_at: datetime
    completed_at: Optional[datetime] = None
    vault: str
    strategy: str
    changes_detected: int
    changes_applied: int
    conflicts: int
    dry_run: bool
    errors: list[dict[str, str]]
    changes: list[ObsidianSyncChange]


class ObsidianSyncStatus(BaseModel):
    """Status of sync tracking."""

    total_tracked: int
    never_synced: int
    synced_recently: int
    storage_path: str


class SyncCheckRequest(BaseModel):
    """Request to check sync status between OpenBrain and Obsidian for a single record."""

    memory_id: Optional[str] = Field(default=None, max_length=64)
    match_key: Optional[MatchKeyStr] = None
    obsidian_ref: Optional[PathStr] = None
    file_hash: Optional[Annotated[str, Field(max_length=64)]] = None

    @model_validator(mode="after")
    def validate_identifier_count(self) -> "SyncCheckRequest":
        """Ensure exactly one identifier field is provided."""
        identifiers = [self.memory_id, self.match_key, self.obsidian_ref]
        provided = [value for value in identifiers if value]
        if len(provided) != 1:
            raise ValueError(
                "Exactly one of memory_id, match_key, or obsidian_ref must be provided."
            )
        return self


class SyncCheckResponse(BaseModel):
    """Response reporting whether a record is in sync between OpenBrain and Obsidian."""

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
    """Response envelope for a single memory write operation."""

    status: Literal["created", "updated", "versioned", "skipped", "failed"]
    record: Optional[MemoryRecord] = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BatchResultItem(BaseModel):
    """Result for a single item within a batch write operation."""

    input_index: int
    status: Literal["created", "updated", "versioned", "skipped", "failed"]
    record_id: Optional[str] = None
    previous_record_id: Optional[str] = None
    match_key: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class MemoryWriteManyResponse(BaseModel):
    """Response envelope for a batch write operation with per-record results."""

    status: Literal["success", "partial_success", "failed"]
    summary: dict[str, int]
    results: list[BatchResultItem]
    errors: list[str] = Field(default_factory=list)


class MemoryGetContextResponse(BaseModel):
    """Response containing a synthesized context pack for grounding an AI response."""

    query: str
    summary: str
    records: list[dict[str, Any]]
    themes: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Legacy compatibility (Deprecated)
# ---------------------------------------------------------------------------


class MemoryCreate(BaseModel):
    """Legacy create request schema; use MemoryWriteRecord for new integrations."""

    content: ContentStr
    domain: Literal["corporate", "build", "personal"] = "corporate"
    entity_type: EntityTypeStr = Field(
        default="Decision", max_length=MAX_ENTITY_TYPE_LEN
    )
    sensitivity: str = "internal"
    owner: OwnerStr = ""
    created_by: str = "agent"
    tags: list[TagStr] = Field(default_factory=list, max_length=MAX_TAGS)
    relations: dict[str, Any] = Field(default_factory=dict)
    obsidian_ref: PathStr | None = None
    match_key: MatchKeyStr | None = None
    tenant_id: TenantIdStr | None = None
    status: Literal["active", "draft", "deprecated"] = "active"
    valid_from: Optional[datetime] = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("custom_fields", mode="before")
    @classmethod
    def _check_custom_fields(cls, v: Any) -> Any:
        """Delegate to shared custom_fields validator."""
        return _validate_custom_fields(v) if v is not None else {}


class MemoryUpdate(BaseModel):
    """Partial update payload; only provided fields are applied to the existing record."""

    content: Optional[ContentStr] = None
    title: Optional[TitleStr] = None
    updated_by: str = "agent"
    sensitivity: Optional[str] = None
    owner: Optional[OwnerStr] = None
    tags: Optional[list[TagStr]] = Field(default=None, max_length=MAX_TAGS)
    relations: Optional[dict[str, Any]] = None
    obsidian_ref: Optional[PathStr] = None
    tenant_id: Optional[TenantIdStr] = None
    custom_fields: Optional[dict[str, Any]] = None

    @field_validator("custom_fields", mode="before")
    @classmethod
    def _check_custom_fields(cls, v: Any) -> Any:
        """Delegate to shared custom_fields validator (None is allowed for partial updates)."""
        return _validate_custom_fields(v) if v is not None else v


class MemoryUpsertItem(BaseModel):
    """Single item in a bulk upsert request; requires match_key for idempotent writes."""

    content: ContentStr
    domain: Literal["corporate", "build", "personal"] = "corporate"
    entity_type: EntityTypeStr = Field(
        default="Decision", max_length=MAX_ENTITY_TYPE_LEN
    )
    sensitivity: str = "internal"
    owner: OwnerStr = ""
    created_by: str = "agent"
    tags: list[TagStr] = Field(default_factory=list, max_length=MAX_TAGS)
    relations: dict[str, Any] = Field(default_factory=dict)
    obsidian_ref: PathStr | None = None
    match_key: MatchKeyStr | None = None
    tenant_id: TenantIdStr | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("custom_fields", mode="before")
    @classmethod
    def _check_custom_fields(cls, v: Any) -> Any:
        """Delegate to shared custom_fields validator."""
        return _validate_custom_fields(v) if v is not None else {}


class SearchRequest(BaseModel):
    """Request for semantic vector search over memories."""

    query: QueryStr
    top_k: int = Field(default=5, ge=1, le=MAX_FILTER_LIMIT)
    filters: dict[str, Any] = Field(default_factory=dict)


class ExportRequest(BaseModel):
    """Request to export specific memory records by ID."""

    ids: list[Annotated[str, Field(max_length=64)]] = Field(max_length=MAX_EXPORT_IDS)
    format: Literal["jsonl", "json"] = "json"


class MaintenanceRequest(BaseModel):
    """Request to run a maintenance pass (dedup, owner normalization, link repair)."""

    dry_run: bool = True
    dedup_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    normalize_owners: dict[str, str] = Field(
        default_factory=dict, max_length=MAX_POLICY_REWRITES
    )
    retype_rules: list[dict[str, str]] = Field(
        default_factory=list, max_length=MAX_POLICY_REWRITES
    )
    fix_superseded_links: bool = True
    allow_exact_dedup_override: bool = False
    """When True, exact content-hash duplicates in append-only domains are superseded
    (governance-safe: canonical record is preserved, no content is changed or deleted).
    Requires explicit opt-in to prevent accidental mutation of audited records."""


class MemoryOut(BaseModel):
    """Flattened memory record returned to API clients."""

    id: str
    tenant_id: Optional[TenantIdStr] = None
    domain: str
    entity_type: EntityTypeStr
    content: ContentStr
    owner: OwnerStr
    status: str
    version: int
    sensitivity: str
    superseded_by: Optional[str] = None
    tags: list[TagStr] = Field(default_factory=list, max_length=MAX_TAGS)
    relations: dict[str, Any] = Field(default_factory=dict)
    obsidian_ref: Optional[PathStr] = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""
    match_key: Optional[MatchKeyStr] = None
    previous_id: Optional[str] = None
    root_id: Optional[str] = None
    valid_from: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str = ""

    model_config = {"from_attributes": True}

    @field_validator("custom_fields", mode="before")
    @classmethod
    def _check_custom_fields(cls, v: Any) -> Any:
        """Delegate to shared custom_fields validator."""
        return _validate_custom_fields(v) if v is not None else {}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def title(self) -> Optional[str]:
        """Return title from custom_fields, if present and non-empty."""
        v = self.custom_fields.get("title")
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None


class SearchResult(BaseModel):
    """A single search result pairing a memory record with its relevance score."""

    memory: MemoryOut
    score: float


class BulkUpsertResult(BaseModel):
    """Result of a bulk upsert operation categorized by outcome."""

    inserted: list[MemoryOut] = Field(default_factory=list)
    updated: list[MemoryOut] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


class MaintenanceAction(BaseModel):
    """Single action taken or proposed during a maintenance run."""

    action: str
    memory_id: str
    detail: str


class MaintenanceReport(BaseModel):
    """Summary report produced at the end of a maintenance run."""

    report_id: Optional[str] = None
    dry_run: bool
    actions: list[MaintenanceAction] = Field(default_factory=list)
    total_scanned: int = 0
    dedup_found: int = 0
    owners_normalized: int = 0
    links_fixed: int = 0


class MaintenanceReportEntry(BaseModel):
    """Lightweight maintenance report entry for listing past runs."""

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
    """Full maintenance report with individual action log for a single run."""

    report_id: str
    created_at: datetime
    actor: str
    dry_run: bool
    actions: list[MaintenanceAction] = Field(default_factory=list)
    total_scanned: int = 0
    dedup_found: int = 0
    owners_normalized: int = 0
    links_fixed: int = 0


class TestDataSampleEntry(BaseModel):
    """A single sampled record from the test data hygiene report."""

    id: str
    domain: str
    status: str
    owner: str
    match_key: str | None = None
    created_at: datetime
    updated_at: datetime


class TestDataActionSuggestion(BaseModel):
    """A recommended remediation action from the test data hygiene report."""

    code: str
    priority: Literal["low", "medium", "high"]
    summary: str


class BuildTestDataCleanupRequest(BaseModel):
    """Request to delete build-domain test data records."""

    dry_run: bool = True
    limit: int = Field(default=100, ge=1, le=500)


class BuildTestDataCleanupSkip(BaseModel):
    """A record that was skipped during cleanup with the reason it was excluded."""

    id: str
    reason: str


class BuildTestDataCleanupResponse(BaseModel):
    """Response from a build-domain test data cleanup operation."""

    dry_run: bool
    scanned: int = 0
    candidates_count: int = 0
    deleted_count: int = 0
    skipped_count: int = 0
    candidate_ids: list[str] = Field(default_factory=list)
    deleted_ids: list[str] = Field(default_factory=list)
    skipped: list[BuildTestDataCleanupSkip] = Field(default_factory=list)


class TestDataHygieneReport(BaseModel):
    """Read-only hygiene report for records flagged as test data."""

    generated_at: datetime
    sample_limit: int
    visible_status_counts: dict[str, int] = Field(default_factory=dict)
    visible_domain_status_counts: dict[str, dict[str, int]] = Field(
        default_factory=dict
    )
    hidden_counts: dict[str, int] = Field(default_factory=dict)
    hidden_active_ratio: float = 0.0
    hidden_active_ratio_by_domain: dict[str, float] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)
    domain_status_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    top_owners: dict[str, int] = Field(default_factory=dict)
    match_key_prefix_counts: dict[str, int] = Field(default_factory=dict)
    null_match_key_count: int = 0
    recommended_actions: list[TestDataActionSuggestion] = Field(default_factory=list)
    sample: list[TestDataSampleEntry] = Field(default_factory=list)


class PolicyScopeEntry(BaseModel):
    """Domain-access policy for a single tenant or subject."""

    allowed_domains: list[Literal["corporate", "build", "personal"]] = Field(
        default_factory=list
    )
    read_domains: list[Literal["corporate", "build", "personal"]] = Field(
        default_factory=list
    )
    write_domains: list[Literal["corporate", "build", "personal"]] = Field(
        default_factory=list
    )
    admin_domains: list[Literal["corporate", "build", "personal"]] = Field(
        default_factory=list
    )


class PolicyRegistry(BaseModel):
    """Access control registry mapping tenants and subjects to their domain policies."""

    tenants: dict[str, PolicyScopeEntry] = Field(default_factory=dict)
    subjects: dict[str, PolicyScopeEntry] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Error Models
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """Structured error information returned in error responses."""

    code: str
    message: str
    details: Optional[dict[str, Any]] = None
    retryable: bool = False


class ErrorEnvelope(BaseModel):
    """Top-level error response envelope wrapping a structured error detail."""

    error: ErrorDetail
