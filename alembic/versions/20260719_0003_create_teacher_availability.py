"""create teacher availability

Revision ID: 20260719_0003
Revises: 20260719_0002
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260719_0003"
down_revision: str | None = "20260719_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

day_of_week = postgresql.ENUM(
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    name="day_of_week",
    create_type=False,
)
availability_slot_source = postgresql.ENUM(
    "rule",
    "manual",
    name="availability_slot_source",
    create_type=False,
)
availability_slot_status = postgresql.ENUM(
    "available",
    "booked",
    "cancelled",
    "blocked",
    name="availability_slot_status",
    create_type=False,
)


def upgrade() -> None:
    day_of_week.create(op.get_bind(), checkfirst=True)
    availability_slot_source.create(op.get_bind(), checkfirst=True)
    availability_slot_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "teacher_availability_rules",
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("day_of_week", day_of_week, nullable=False),
        sa.Column("start_time_utc", sa.Time(), nullable=False),
        sa.Column("end_time_utc", sa.Time(), nullable=False),
        sa.Column("slot_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
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
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_teacher_availability_rules_teacher_id"),
        "teacher_availability_rules",
        ["teacher_id"],
        unique=False,
    )

    op.create_table(
        "teacher_availability_slots",
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=True),
        sa.Column("source", availability_slot_source, nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", availability_slot_status, nullable=False),
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
            ["rule_id"],
            ["teacher_availability_rules.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_teacher_availability_slots_rule_id"),
        "teacher_availability_slots",
        ["rule_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teacher_availability_slots_teacher_id"),
        "teacher_availability_slots",
        ["teacher_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_teacher_availability_slots_teacher_id"),
        table_name="teacher_availability_slots",
    )
    op.drop_index(
        op.f("ix_teacher_availability_slots_rule_id"),
        table_name="teacher_availability_slots",
    )
    op.drop_table("teacher_availability_slots")

    op.drop_index(
        op.f("ix_teacher_availability_rules_teacher_id"),
        table_name="teacher_availability_rules",
    )
    op.drop_table("teacher_availability_rules")

    availability_slot_status.drop(op.get_bind(), checkfirst=True)
    availability_slot_source.drop(op.get_bind(), checkfirst=True)
    day_of_week.drop(op.get_bind(), checkfirst=True)
