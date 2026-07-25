"""add student assigned teacher

Revision ID: 20260723_0017
Revises: 20260722_0016
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260723_0017"
down_revision: str | None = "20260722_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "students",
        sa.Column("assigned_teacher_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_students_assigned_teacher_id_teachers",
        "students",
        "teachers",
        ["assigned_teacher_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_students_assigned_teacher_id"),
        "students",
        ["assigned_teacher_id"],
    )
    op.create_check_constraint(
        "ck_students_assigned_teacher_one_on_one",
        "students",
        "program_type = 'one_on_one' OR assigned_teacher_id IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_students_assigned_teacher_one_on_one",
        "students",
        type_="check",
    )
    op.drop_index(op.f("ix_students_assigned_teacher_id"), table_name="students")
    op.drop_constraint(
        "fk_students_assigned_teacher_id_teachers",
        "students",
        type_="foreignkey",
    )
    op.drop_column("students", "assigned_teacher_id")
