"""create booking events

Revision ID: 20260721_0012
Revises: 20260721_0011
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260721_0012"
down_revision: str | None = "20260721_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

booking_event_type = postgresql.ENUM(
    "booked",
    "cancelled_by_student",
    "cancelled_by_admin",
    "rescheduled_from",
    "rescheduled_to",
    "class_cancelled_empty",
    name="booking_event_type",
    create_type=False,
)


def upgrade() -> None:
    booking_event_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "booking_events",
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", booking_event_type, nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_booking_events_actor_user_id"),
        "booking_events",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_booking_events_booking_id"),
        "booking_events",
        ["booking_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_booking_events_event_type"),
        "booking_events",
        ["event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_booking_events_event_type"), table_name="booking_events")
    op.drop_index(op.f("ix_booking_events_booking_id"), table_name="booking_events")
    op.drop_index(op.f("ix_booking_events_actor_user_id"), table_name="booking_events")
    op.drop_table("booking_events")

    booking_event_type.drop(op.get_bind(), checkfirst=True)
