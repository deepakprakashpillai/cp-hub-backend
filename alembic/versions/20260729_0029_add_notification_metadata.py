"""Add structured notification metadata.

Revision ID: 20260729_0029
Revises: 20260727_0028
Create Date: 2026-07-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20260729_0029"
down_revision = "20260727_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("notifications", "metadata")
