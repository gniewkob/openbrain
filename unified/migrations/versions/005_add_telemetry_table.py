"""add telemetry persistence table

Revision ID: 005_add_telemetry_table
Revises: 004_add_tenant_id_column
Create Date: 2026-03-31 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_add_telemetry_table"
down_revision: Union[str, None] = "004_add_tenant_id_column"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telemetry_counters",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("name")
    )


def downgrade() -> None:
    op.drop_table("telemetry_counters")
