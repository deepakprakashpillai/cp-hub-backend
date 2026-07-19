"""create student payments table

Revision ID: 20260719_0007
Revises: 20260719_0006
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260719_0007"
down_revision: str | None = "20260719_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

payment_method = postgresql.ENUM(
    "upi",
    "cash",
    "bank_transfer",
    "other",
    name="payment_method",
    create_type=False,
)


def upgrade() -> None:
    payment_method.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "student_payments",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("package_id", sa.Uuid(), nullable=True),
        sa.Column("amount_paid", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("payment_method", payment_method, nullable=False),
        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
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
            "amount_paid >= 0",
            name="ck_student_payments_amount_paid_non_negative",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["package_id"], ["packages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_student_payments_created_by_user_id"),
        "student_payments",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_payments_package_id"),
        "student_payments",
        ["package_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_payments_student_id"),
        "student_payments",
        ["student_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_student_payments_student_id"), table_name="student_payments")
    op.drop_index(op.f("ix_student_payments_package_id"), table_name="student_payments")
    op.drop_index(
        op.f("ix_student_payments_created_by_user_id"),
        table_name="student_payments",
    )
    op.drop_table("student_payments")

    payment_method.drop(op.get_bind(), checkfirst=True)
