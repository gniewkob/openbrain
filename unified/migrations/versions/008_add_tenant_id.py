"""Add tenant_id column to memories table.

Revision ID: 008_tenant_id
Revises: 007_auditlog_ctx
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa

revision = "008_tenant_id"
down_revision = "007_auditlog_ctx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memories",
        sa.Column("tenant_id", sa.String(128), nullable=True),
    )
    op.create_index("ix_memories_tenant_id", "memories", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_memories_tenant_id", table_name="memories")
    op.drop_column("memories", "tenant_id")
