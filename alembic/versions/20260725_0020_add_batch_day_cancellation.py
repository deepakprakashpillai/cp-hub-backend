"""add batch schedule day cancellation

Revision ID: 20260725_0020
Revises: 20260725_0019
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260725_0020"
down_revision: str | None = "20260725_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE booking_event_type ADD VALUE IF NOT EXISTS 'batch_day_cancelled'")
    day_status = sa.Enum("scheduled", "cancelled", name="batch_schedule_day_status")
    day_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "batch_schedule_days",
        sa.Column(
            "status",
            day_status,
            server_default="scheduled",
            nullable=False,
        ),
    )
    op.add_column(
        "batch_schedule_days",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "batch_schedule_days",
        sa.Column("cancelled_by_user_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "batch_schedule_days",
        sa.Column("cancel_reason", sa.String(length=1000), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_batch_schedule_days_cancelled_by_user_id_users"),
        "batch_schedule_days",
        "users",
        ["cancelled_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "batch_schedule_day_events",
        sa.Column("batch_schedule_day_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("metadata", sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["batch_schedule_day_id"],
            ["batch_schedule_days.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_batch_schedule_day_events_actor_user_id"),
        "batch_schedule_day_events",
        ["actor_user_id"],
    )
    op.create_index(
        op.f("ix_batch_schedule_day_events_batch_schedule_day_id"),
        "batch_schedule_day_events",
        ["batch_schedule_day_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_batch_schedule_day_events_batch_schedule_day_id"),
        table_name="batch_schedule_day_events",
    )
    op.drop_index(
        op.f("ix_batch_schedule_day_events_actor_user_id"),
        table_name="batch_schedule_day_events",
    )
    op.drop_table("batch_schedule_day_events")
    op.drop_constraint(
        op.f("fk_batch_schedule_days_cancelled_by_user_id_users"),
        "batch_schedule_days",
        type_="foreignkey",
    )
    op.drop_column("batch_schedule_days", "cancel_reason")
    op.drop_column("batch_schedule_days", "cancelled_by_user_id")
    op.drop_column("batch_schedule_days", "cancelled_at")
    op.drop_column("batch_schedule_days", "status")
    sa.Enum(name="batch_schedule_day_status").drop(op.get_bind(), checkfirst=True)
