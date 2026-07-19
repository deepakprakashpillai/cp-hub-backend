"""create student access grants table

Revision ID: 20260719_0008
Revises: 20260719_0007
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260719_0008"
down_revision: str | None = "20260719_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

student_access_grant_type = postgresql.ENUM(
    "package",
    "addon_days",
    "manual_adjustment",
    name="student_access_grant_type",
    create_type=False,
)


def upgrade() -> None:
    student_access_grant_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "student_access_grants",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("package_id", sa.Uuid(), nullable=True),
        sa.Column("grant_type", student_access_grant_type, nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("access_starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("access_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "duration_days > 0",
            name="ck_student_access_grants_duration_days_positive",
        ),
        sa.CheckConstraint(
            "access_starts_at < access_ends_at",
            name="ck_student_access_grants_access_window_valid",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["package_id"], ["packages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_student_access_grants_created_by_user_id"),
        "student_access_grants",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_access_grants_package_id"),
        "student_access_grants",
        ["package_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_access_grants_student_id"),
        "student_access_grants",
        ["student_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_student_access_grants_student_id"),
        table_name="student_access_grants",
    )
    op.drop_index(
        op.f("ix_student_access_grants_package_id"),
        table_name="student_access_grants",
    )
    op.drop_index(
        op.f("ix_student_access_grants_created_by_user_id"),
        table_name="student_access_grants",
    )
    op.drop_table("student_access_grants")

    student_access_grant_type.drop(op.get_bind(), checkfirst=True)
