"""create students table

Revision ID: 20260719_0005
Revises: 20260719_0004
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260719_0005"
down_revision: str | None = "20260719_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

student_program_type = postgresql.ENUM(
    "one_on_one",
    "batch",
    name="student_program_type",
    create_type=False,
)
student_status = postgresql.ENUM(
    "enrolled",
    "active",
    "paused",
    "completed",
    "cancelled",
    name="student_status",
    create_type=False,
)


def upgrade() -> None:
    student_program_type.create(op.get_bind(), checkfirst=True)
    student_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "students",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("program_type", student_program_type, nullable=False),
        sa.Column("status", student_status, server_default="enrolled", nullable=False),
        sa.Column("access_starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("notes", sa.String(length=1000), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_students_user_id"), "students", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_students_user_id"), table_name="students")
    op.drop_table("students")

    student_status.drop(op.get_bind(), checkfirst=True)
    student_program_type.drop(op.get_bind(), checkfirst=True)
