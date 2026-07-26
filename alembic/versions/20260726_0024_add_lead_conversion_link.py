"""add lead conversion link

Revision ID: 20260726_0024
Revises: 20260726_0023
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260726_0024"
down_revision: str | None = "20260726_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("converted_student_id", sa.Uuid(), nullable=True))
    op.add_column("leads", sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_leads_converted_student_id_students",
        "leads",
        "students",
        ["converted_student_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_leads_converted_student_id",
        "leads",
        ["converted_student_id"],
    )
    op.create_index("ix_leads_converted_student_id", "leads", ["converted_student_id"])


def downgrade() -> None:
    op.drop_index("ix_leads_converted_student_id", table_name="leads")
    op.drop_constraint("uq_leads_converted_student_id", "leads", type_="unique")
    op.drop_constraint("fk_leads_converted_student_id_students", "leads", type_="foreignkey")
    op.drop_column("leads", "converted_at")
    op.drop_column("leads", "converted_student_id")
