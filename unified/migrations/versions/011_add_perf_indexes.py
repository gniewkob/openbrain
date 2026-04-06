"""Add performance indexes for sorting and deduplication queries.

Revision ID: 011
Revises: 010
Create Date: 2026-04-06
"""

from alembic import op

revision: str = "011"
down_revision: str = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sorting indexes (used in ORDER BY created_at DESC / updated_at DESC)
    op.create_index(
        "ix_memories_created_at",
        "memories",
        ["created_at"],
        postgresql_using="btree",
    )
    op.create_index(
        "ix_memories_updated_at",
        "memories",
        ["updated_at"],
        postgresql_using="btree",
    )
    # Deduplication: content_hash used in GROUP BY + dedup queries
    op.create_index(
        "ix_memories_content_hash",
        "memories",
        ["content_hash"],
        postgresql_using="btree",
    )


def downgrade() -> None:
    op.drop_index("ix_memories_content_hash", table_name="memories")
    op.drop_index("ix_memories_updated_at", table_name="memories")
    op.drop_index("ix_memories_created_at", table_name="memories")
