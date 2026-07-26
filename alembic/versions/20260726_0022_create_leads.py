"""create leads

Revision ID: 20260726_0022
Revises: 20260725_0021
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260726_0022"
down_revision: str | None = "20260725_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    lead_status = postgresql.ENUM(
        "new",
        "contacted",
        "trial_booked",
        "enrolled",
        "lost",
        name="lead_status",
        create_type=False,
    )
    lead_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("status", lead_status, server_default="new", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_leads_email"), "leads", ["email"])
    op.create_index(op.f("ix_leads_phone"), "leads", ["phone"])
    op.create_index(op.f("ix_leads_status"), "leads", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_leads_status"), table_name="leads")
    op.drop_index(op.f("ix_leads_phone"), table_name="leads")
    op.drop_index(op.f("ix_leads_email"), table_name="leads")
    op.drop_table("leads")
    sa.Enum(name="lead_status").drop(op.get_bind(), checkfirst=True)
