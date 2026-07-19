"""create packages table

Revision ID: 20260719_0006
Revises: 20260719_0005
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260719_0006"
down_revision: str | None = "20260719_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "packages",
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("price_amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
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
        sa.CheckConstraint("duration_days > 0", name="ck_packages_duration_days_positive"),
        sa.CheckConstraint("price_amount >= 0", name="ck_packages_price_amount_non_negative"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("packages")
