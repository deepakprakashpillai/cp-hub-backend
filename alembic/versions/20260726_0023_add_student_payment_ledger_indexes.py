"""add student payment ledger indexes

Revision ID: 20260726_0023
Revises: 20260726_0022
Create Date: 2026-07-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260726_0023"
down_revision: str | None = "20260726_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_student_payments_paid_at", "student_payments", ["paid_at"])
    op.create_index(
        "ix_student_payments_payment_method",
        "student_payments",
        ["payment_method"],
    )


def downgrade() -> None:
    op.drop_index("ix_student_payments_payment_method", table_name="student_payments")
    op.drop_index("ix_student_payments_paid_at", table_name="student_payments")
