"""add admin search indexes

Revision ID: 20260722_0015
Revises: 20260721_0014
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260722_0015"
down_revision: str | None = "20260721_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_index(
        "ix_users_full_name_trgm",
        "users",
        ["full_name"],
        postgresql_using="gin",
        postgresql_ops={"full_name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_users_email_trgm",
        "users",
        ["email"],
        postgresql_using="gin",
        postgresql_ops={"email": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_users_phone_trgm",
        "users",
        ["phone"],
        postgresql_using="gin",
        postgresql_ops={"phone": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_teachers_display_name_trgm",
        "teachers",
        ["display_name"],
        postgresql_using="gin",
        postgresql_ops={"display_name": "gin_trgm_ops"},
    )

    op.create_index(op.f("ix_students_status"), "students", ["status"])
    op.create_index(op.f("ix_students_program_type"), "students", ["program_type"])
    op.create_index(op.f("ix_students_access_starts_at"), "students", ["access_starts_at"])
    op.create_index(op.f("ix_students_access_ends_at"), "students", ["access_ends_at"])
    op.create_index(op.f("ix_teachers_is_active"), "teachers", ["is_active"])


def downgrade() -> None:
    op.drop_index(op.f("ix_teachers_is_active"), table_name="teachers")
    op.drop_index(op.f("ix_students_access_ends_at"), table_name="students")
    op.drop_index(op.f("ix_students_access_starts_at"), table_name="students")
    op.drop_index(op.f("ix_students_program_type"), table_name="students")
    op.drop_index(op.f("ix_students_status"), table_name="students")

    op.drop_index("ix_teachers_display_name_trgm", table_name="teachers", postgresql_using="gin")
    op.drop_index("ix_users_phone_trgm", table_name="users", postgresql_using="gin")
    op.drop_index("ix_users_email_trgm", table_name="users", postgresql_using="gin")
    op.drop_index("ix_users_full_name_trgm", table_name="users", postgresql_using="gin")

    # Leave pg_trgm installed because extensions can be shared by other database objects.
