"""create class sessions and bookings

Revision ID: 20260720_0010
Revises: 20260720_0009
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260720_0010"
down_revision: str | None = "20260720_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

student_program_type = postgresql.ENUM(
    "one_on_one",
    "batch",
    name="student_program_type",
    create_type=False,
)
batch_slot = postgresql.ENUM(
    "morning",
    "noon",
    "afternoon",
    name="batch_slot",
    create_type=False,
)
class_session_status = postgresql.ENUM(
    "scheduled",
    "completed",
    "cancelled",
    name="class_session_status",
    create_type=False,
)
booking_status = postgresql.ENUM(
    "booked",
    "cancelled",
    "attended",
    "missed",
    name="booking_status",
    create_type=False,
)


def upgrade() -> None:
    batch_slot.create(op.get_bind(), checkfirst=True)
    class_session_status.create(op.get_bind(), checkfirst=True)
    booking_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "class_sessions",
        sa.Column("teacher_id", sa.Uuid(), nullable=True),
        sa.Column("teacher_availability_slot_id", sa.Uuid(), nullable=True),
        sa.Column("program_type", student_program_type, nullable=False),
        sa.Column("batch_slot", batch_slot, nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            class_session_status,
            server_default="scheduled",
            nullable=False,
        ),
        sa.Column("capacity", sa.Integer(), server_default="1", nullable=False),
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
        sa.CheckConstraint("starts_at < ends_at", name="ck_class_sessions_time_range_valid"),
        sa.CheckConstraint("capacity > 0", name="ck_class_sessions_capacity_positive"),
        sa.CheckConstraint(
            """
            (
                program_type = 'one_on_one'
                and teacher_id is not null
                and teacher_availability_slot_id is not null
                and batch_slot is null
                and capacity = 1
            )
            or
            (
                program_type = 'batch'
                and teacher_availability_slot_id is null
                and batch_slot is not null
            )
            """,
            name="ck_class_sessions_program_shape",
        ),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["teacher_availability_slot_id"],
            ["teacher_availability_slots.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_class_sessions_program_type"),
        "class_sessions",
        ["program_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_class_sessions_starts_at"),
        "class_sessions",
        ["starts_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_class_sessions_teacher_availability_slot_id"),
        "class_sessions",
        ["teacher_availability_slot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_class_sessions_teacher_id"),
        "class_sessions",
        ["teacher_id"],
        unique=False,
    )
    op.create_index(
        "uq_class_sessions_teacher_availability_slot_id",
        "class_sessions",
        ["teacher_availability_slot_id"],
        unique=True,
        postgresql_where=sa.text(
            "teacher_availability_slot_id is not null and status <> 'cancelled'"
        ),
    )

    op.create_table(
        "bookings",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("class_session_id", sa.Uuid(), nullable=False),
        sa.Column("status", booking_status, server_default="booked", nullable=False),
        sa.Column(
            "booked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
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
        sa.ForeignKeyConstraint(["class_session_id"], ["class_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_bookings_class_session_id"),
        "bookings",
        ["class_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bookings_student_id"),
        "bookings",
        ["student_id"],
        unique=False,
    )
    op.create_index(
        "uq_active_booking_student_class_session",
        "bookings",
        ["student_id", "class_session_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'cancelled'"),
    )


def downgrade() -> None:
    op.drop_index("uq_active_booking_student_class_session", table_name="bookings")
    op.drop_index(op.f("ix_bookings_student_id"), table_name="bookings")
    op.drop_index(op.f("ix_bookings_class_session_id"), table_name="bookings")
    op.drop_table("bookings")

    op.drop_index("uq_class_sessions_teacher_availability_slot_id", table_name="class_sessions")
    op.drop_index(op.f("ix_class_sessions_teacher_id"), table_name="class_sessions")
    op.drop_index(
        op.f("ix_class_sessions_teacher_availability_slot_id"),
        table_name="class_sessions",
    )
    op.drop_index(op.f("ix_class_sessions_starts_at"), table_name="class_sessions")
    op.drop_index(op.f("ix_class_sessions_program_type"), table_name="class_sessions")
    op.drop_table("class_sessions")

    booking_status.drop(op.get_bind(), checkfirst=True)
    class_session_status.drop(op.get_bind(), checkfirst=True)
    batch_slot.drop(op.get_bind(), checkfirst=True)
