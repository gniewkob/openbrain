"""fix uuid columns to string

Revision ID: 010
Revises: 009
Create Date: 2026-04-04 19:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop foreign key constraint first
    op.drop_constraint("memories_superseded_by_fkey", "memories", type_="foreignkey")
    
    # Alter columns from UUID to String
    op.alter_column("memories", "id", type_=sa.String())
    op.alter_column("memories", "superseded_by", type_=sa.String())
    op.alter_column("audit_log", "id", type_=sa.String())
    op.alter_column("audit_log", "memory_id", type_=sa.String())
    
    # Recreate foreign key
    op.create_foreign_key(
        "memories_superseded_by_fkey",
        "memories",
        "memories",
        ["superseded_by"],
        ["id"],
        ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("memories_superseded_by_fkey", "memories", type_="foreignkey")
    
    op.alter_column("memories", "id", type_=sa.UUID())
    op.alter_column("memories", "superseded_by", type_=sa.UUID())
    op.alter_column("audit_log", "id", type_=sa.UUID())
    op.alter_column("audit_log", "memory_id", type_=sa.UUID())
    
    op.create_foreign_key(
        "memories_superseded_by_fkey",
        "memories",
        "memories",
        ["superseded_by"],
        ["id"],
        ondelete="SET NULL"
    )
