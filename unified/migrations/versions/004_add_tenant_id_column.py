"""add first-class tenant_id column to memories

Revision ID: 004_add_tenant_id_column
Revises: 003_match_key_unique_active
Create Date: 2026-03-30 19:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_add_tenant_id_column"
down_revision: Union[str, None] = "003_match_key_unique_active"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("memories", sa.Column("tenant_id", sa.String(length=128), nullable=True))
    op.create_index("ix_memories_tenant_id", "memories", ["tenant_id"], unique=False)
    op.execute(
        """
        UPDATE memories
        SET tenant_id = metadata->>'tenant_id'
        WHERE tenant_id IS NULL
          AND metadata ? 'tenant_id'
          AND metadata->>'tenant_id' IS NOT NULL
          AND metadata->>'tenant_id' <> ''
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE memories
        SET metadata = jsonb_set(
            COALESCE(metadata, '{}'::jsonb),
            '{tenant_id}',
            to_jsonb(tenant_id::text),
            true
        )
        WHERE tenant_id IS NOT NULL
        """
    )
    op.drop_index("ix_memories_tenant_id", table_name="memories")
    op.drop_column("memories", "tenant_id")
