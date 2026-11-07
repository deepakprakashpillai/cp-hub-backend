"""add teacher class cancellation event

Revision ID: 20260727_0027
Revises: 20260726_0026
Create Date: 2026-07-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260727_0027"
down_revision: str | None = "20260726_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE booking_event_type ADD VALUE IF NOT EXISTS 'cancelled_by_teacher'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely in place.
    pass
