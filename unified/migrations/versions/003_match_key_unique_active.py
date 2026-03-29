"""add partial unique index on match_key for active memories

Revision ID: 003_match_key_unique_active
Revises: 002_add_governance_columns
Create Date: 2026-03-29 09:00:00.000000

Closes the TOCTOU race window for concurrent writes with the same match_key.

A *partial* unique index is used instead of a plain UNIQUE constraint because:
  - Version chains share the same match_key: when a corporate record is versioned,
    the old row becomes status='superseded' before the new row is inserted, so
    only one row with a given match_key ever has status='active' at a time.
  - NULL match_keys are excluded so records without an idempotency key
    can coexist freely.

The index form is:
  CREATE UNIQUE INDEX uq_memories_match_key_active
    ON memories (match_key)
    WHERE status = 'active' AND match_key IS NOT NULL;
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_match_key_unique_active"
down_revision: Union[str, None] = "002_add_governance_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old plain index first (will be superseded by the partial unique one)
    op.drop_index("ix_memories_match_key", table_name="memories", if_exists=True)

    # Partial unique index: at most one *active* record per match_key.
    op.execute("""
        CREATE UNIQUE INDEX uq_memories_match_key_active
          ON memories (match_key)
          WHERE status = 'active' AND match_key IS NOT NULL
    """)

    # Retain a non-unique index for querying all versions by match_key
    # (e.g. listing the full version history of a corporate record).
    op.create_index(
        "ix_memories_match_key_all",
        "memories",
        ["match_key"],
        unique=False,
        postgresql_where=sa.text("match_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_memories_match_key_all", table_name="memories")
    op.execute("DROP INDEX IF EXISTS uq_memories_match_key_active")
    op.create_index("ix_memories_match_key", "memories", ["match_key"])
