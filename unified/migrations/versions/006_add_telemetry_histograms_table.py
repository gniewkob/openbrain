"""add telemetry histograms table

Revision ID: 006_telemetry_hist
Revises: 005_add_telemetry_table
Create Date: 2026-04-01 00:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006_telemetry_hist"
down_revision: Union[str, None] = "005_add_telemetry_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telemetry_histograms",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("sum", sa.Float(), nullable=False, server_default="0"),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "buckets",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "counts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("telemetry_histograms")
