"""link batch groups to packages

Revision ID: 20260725_0021
Revises: 20260725_0020
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260725_0021"
down_revision: str | None = "20260725_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "batch_groups",
        sa.Column("package_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_batch_groups_package_id_packages"),
        "batch_groups",
        "packages",
        ["package_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_batch_groups_package_id"),
        "batch_groups",
        ["package_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_batch_groups_package_id"),
        table_name="batch_groups",
    )
    op.drop_constraint(
        op.f("fk_batch_groups_package_id_packages"),
        "batch_groups",
        type_="foreignkey",
    )
    op.drop_column("batch_groups", "package_id")
