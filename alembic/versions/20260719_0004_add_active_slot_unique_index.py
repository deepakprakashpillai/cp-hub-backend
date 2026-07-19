"""add active slot unique index

Revision ID: 20260719_0004
Revises: 20260719_0003
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260719_0004"
down_revision: str | None = "20260719_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_active_teacher_availability_slot_time",
        "teacher_availability_slots",
        ["teacher_id", "starts_at", "ends_at"],
        unique=True,
        postgresql_where=sa.text("status <> 'cancelled'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_active_teacher_availability_slot_time",
        table_name="teacher_availability_slots",
    )
