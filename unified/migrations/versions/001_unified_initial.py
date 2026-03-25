"""unified initial schema — full governance model

Revision ID: 001_unified_initial
Revises:
Create Date: 2026-03-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector
from sqlalchemy.dialects import postgresql

revision: str = "001_unified_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # domain enum
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'domainenum') THEN "
        "CREATE TYPE domainenum AS ENUM ('corporate', 'build', 'personal'); "
        "END IF; END $$;"
    )

    # --- memories table ---
    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("domain_temp", sa.String(32), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=True),
        # governance
        sa.Column("owner", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(128), nullable=False, server_default="agent"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sensitivity", sa.String(32), nullable=False, server_default="internal"),
        sa.Column("superseded_by", postgresql.UUID(as_uuid=False), nullable=True),
        # tags & relations
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("relations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        # obsidian sync
        sa.Column("obsidian_ref", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        # idempotent upsert
        sa.Column("match_key", sa.String(256), nullable=True),
        # timestamps
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        # constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["superseded_by"], ["memories.id"], ondelete="SET NULL"),
    )

    # Cast domain column to enum
    op.execute("ALTER TABLE memories RENAME COLUMN domain_temp TO domain")
    op.execute("ALTER TABLE memories ALTER COLUMN domain TYPE domainenum USING domain::domainenum")

    # Indexes
    op.create_index("ix_memories_domain", "memories", ["domain"])
    op.create_index("ix_memories_entity_type", "memories", ["entity_type"])
    op.create_index("ix_memories_status", "memories", ["status"])
    op.create_index("ix_memories_status_entity", "memories", ["status", "entity_type"])
    op.create_index("ix_memories_obsidian_ref", "memories", ["obsidian_ref"])
    op.create_index("ix_memories_match_key", "memories", ["match_key"])
    op.execute(
        "CREATE INDEX ix_memories_embedding_hnsw ON memories "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )

    # --- audit_log table ---
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("memory_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("actor", sa.String(128), nullable=False, server_default="agent"),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_index("ix_memories_embedding_hnsw", table_name="memories", postgresql_using="hnsw")
    op.drop_index("ix_memories_match_key", table_name="memories")
    op.drop_index("ix_memories_obsidian_ref", table_name="memories")
    op.drop_index("ix_memories_status_entity", table_name="memories")
    op.drop_index("ix_memories_status", table_name="memories")
    op.drop_index("ix_memories_entity_type", table_name="memories")
    op.drop_index("ix_memories_domain", table_name="memories")
    op.drop_table("memories")
    op.execute("DROP TYPE IF EXISTS domainenum")
