"""add governance columns to existing memories table

Revision ID: 002_add_governance_columns
Revises: 001_unified_initial
Create Date: 2026-03-24 12:00:00.000000

Adds missing columns for unified governance model without losing existing data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002_add_governance_columns"
down_revision: Union[str, None] = "001_unified_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add governance columns with defaults
    op.add_column("memories", sa.Column("owner", sa.String(128), nullable=False, server_default=""))
    op.add_column("memories", sa.Column("created_by", sa.String(128), nullable=False, server_default="agent"))
    op.add_column("memories", sa.Column("status", sa.String(32), nullable=False, server_default="active"))
    op.add_column("memories", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("memories", sa.Column("sensitivity", sa.String(32), nullable=False, server_default="internal"))
    op.add_column("memories", sa.Column("superseded_by", sa.String(), nullable=True))
    op.add_column("memories", sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("memories", sa.Column("match_key", sa.String(256), nullable=True))
    op.add_column("memories", sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True))

    # Skip FK constraint — id is varchar, not uuid in existing table

    # Indexes
    op.create_index("ix_memories_status", "memories", ["status"])
    op.create_index("ix_memories_status_entity", "memories", ["status", "entity_type"])
    op.create_index("ix_memories_match_key", "memories", ["match_key"])

    # Migrate old_tags from metadata JSONB to tags ARRAY column
    op.execute("""
        UPDATE memories
        SET tags = ARRAY(SELECT jsonb_array_elements_text(metadata->'old_tags'))
        WHERE metadata ? 'old_tags'
          AND jsonb_typeof(metadata->'old_tags') = 'array'
    """)

    # Create audit_log table
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("memory_id", sa.String(), nullable=True),
        sa.Column("actor", sa.String(128), nullable=False, server_default="agent"),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_index("ix_memories_match_key", table_name="memories")
    op.drop_index("ix_memories_status_entity", table_name="memories")
    op.drop_index("ix_memories_status", table_name="memories")
    op.drop_constraint("fk_memories_superseded_by", "memories", type_="foreignkey")
    op.drop_column("memories", "valid_from")
    op.drop_column("memories", "match_key")
    op.drop_column("memories", "tags")
    op.drop_column("memories", "superseded_by")
    op.drop_column("memories", "sensitivity")
    op.drop_column("memories", "version")
    op.drop_column("memories", "status")
    op.drop_column("memories", "created_by")
    op.drop_column("memories", "owner")
