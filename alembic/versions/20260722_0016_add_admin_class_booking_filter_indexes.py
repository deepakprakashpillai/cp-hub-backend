"""add admin class booking filter indexes

Revision ID: 20260722_0016
Revises: 20260722_0015
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260722_0016"
down_revision: str | None = "20260722_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(op.f("ix_class_sessions_status"), "class_sessions", ["status"])
    op.create_index(op.f("ix_bookings_status"), "bookings", ["status"])
    op.create_index(op.f("ix_bookings_booked_at"), "bookings", ["booked_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_bookings_booked_at"), table_name="bookings")
    op.drop_index(op.f("ix_bookings_status"), table_name="bookings")
    op.drop_index(op.f("ix_class_sessions_status"), table_name="class_sessions")
