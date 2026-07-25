"""create booking notes

Revision ID: 20260724_0018
Revises: 20260723_0017
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260724_0018"
down_revision: str | None = "20260723_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

booking_note_visibility = postgresql.ENUM(
    "admin_only",
    "student_visible",
    name="booking_note_visibility",
    create_type=False,
)


def upgrade() -> None:
    booking_note_visibility.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "booking_notes",
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("class_session_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.String(length=2000), nullable=False),
        sa.Column(
            "visibility",
            booking_note_visibility,
            server_default="admin_only",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["class_session_id"],
            ["class_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_booking_notes_booking_id"), "booking_notes", ["booking_id"])
    op.create_index(
        op.f("ix_booking_notes_class_session_id"),
        "booking_notes",
        ["class_session_id"],
    )
    op.create_index(op.f("ix_booking_notes_student_id"), "booking_notes", ["student_id"])
    op.create_index(op.f("ix_booking_notes_teacher_id"), "booking_notes", ["teacher_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_booking_notes_teacher_id"), table_name="booking_notes")
    op.drop_index(op.f("ix_booking_notes_student_id"), table_name="booking_notes")
    op.drop_index(op.f("ix_booking_notes_class_session_id"), table_name="booking_notes")
    op.drop_index(op.f("ix_booking_notes_booking_id"), table_name="booking_notes")
    op.drop_table("booking_notes")
    booking_note_visibility.drop(op.get_bind(), checkfirst=True)
