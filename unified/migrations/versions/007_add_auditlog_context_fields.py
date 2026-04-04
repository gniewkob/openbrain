"""add actor_ip, request_id, authorization_context to audit_log

Revision ID: 007_auditlog_ctx
Revises: 006_telemetry_hist
Create Date: 2026-04-04 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_auditlog_ctx"
down_revision: Union[str, None] = "006_telemetry_hist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("actor_ip", sa.String(45), nullable=True))
    op.add_column("audit_log", sa.Column("request_id", sa.String(64), nullable=True))
    op.add_column(
        "audit_log",
        sa.Column("authorization_context", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("audit_log", "authorization_context")
    op.drop_column("audit_log", "request_id")
    op.drop_column("audit_log", "actor_ip")
