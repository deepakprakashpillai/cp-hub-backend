"""add attendance marked booking event

Revision ID: 20260721_0013
Revises: 20260721_0012
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260721_0013"
down_revision: str | None = "20260721_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE booking_event_type ADD VALUE IF NOT EXISTS 'attendance_marked'")


def downgrade() -> None:
    pass
