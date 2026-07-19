"""create student program changes table

Revision ID: 20260720_0009
Revises: 20260719_0008
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260720_0009"
down_revision: str | None = "20260719_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

student_program_type = postgresql.ENUM(
    "one_on_one",
    "batch",
    name="student_program_type",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "student_program_changes",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("old_program_type", student_program_type, nullable=False),
        sa.Column("new_program_type", student_program_type, nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=1000), nullable=True),
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
        sa.CheckConstraint(
            "old_program_type <> new_program_type",
            name="ck_student_program_changes_program_changed",
        ),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_student_program_changes_changed_by_user_id"),
        "student_program_changes",
        ["changed_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_program_changes_student_id"),
        "student_program_changes",
        ["student_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_student_program_changes_student_id"),
        table_name="student_program_changes",
    )
    op.drop_index(
        op.f("ix_student_program_changes_changed_by_user_id"),
        table_name="student_program_changes",
    )
    op.drop_table("student_program_changes")
