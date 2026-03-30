"""
OpenBrain Unified v2.0 — Data Models.

Single Memory table with domain-aware governance:
  - corporate: append-only versioning, audit trail, sensitivity levels
  - build/personal: mutable, delete allowed, lightweight
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Enum,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

EMBEDDING_DIM = 768  # nomic-embed-text


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


def compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class DomainEnum(str, PyEnum):
    corporate = "corporate"
    build = "build"
    personal = "personal"


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(
        String(), primary_key=True, default=_uuid
    )

    # --- Domain ---
    domain: Mapped[DomainEnum] = mapped_column(
        Enum(DomainEnum, name="domainenum", create_type=False),
        nullable=False,
        index=True,
    )

    # --- Core fields ---
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    # --- Governance (from old work-brain) ---
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="agent")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sensitivity: Mapped[str] = mapped_column(
        String(32), nullable=False, default="internal"
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(), nullable=True,
    )

    # --- Tagging & relations ---
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    relations: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    # --- Obsidian sync ---
    obsidian_ref: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    # --- Idempotent upsert ---
    # The plain index=True is kept for all-version history lookups.
    # A partial unique index (status='active' AND match_key IS NOT NULL) is
    # created by migration 003 to enforce at most one active record per match_key.
    match_key: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # --- Timestamps ---
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    __table_args__ = (
        Index(
            "ix_memories_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_memories_status_entity", "status", "entity_type"),
        # All-version history lookup (non-unique, skips NULLs)
        Index(
            "ix_memories_match_key_all",
            "match_key",
            postgresql_where=sa_text("match_key IS NOT NULL"),
        ),
        # Partial unique index: at most one *active* record per match_key.
        # Created/enforced by migration 003. Declared here so autogenerate stays in sync.
        Index(
            "uq_memories_match_key_active",
            "match_key",
            unique=True,
            postgresql_where=sa_text("status = 'active' AND match_key IS NOT NULL"),
        ),
    )


class AuditLog(Base):
    """Immutable audit trail — corporate domain operations only."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(
        String(), primary_key=True, default=_uuid
    )
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    memory_id: Mapped[str | None] = mapped_column(
        String(), nullable=True
    )
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="agent")
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
