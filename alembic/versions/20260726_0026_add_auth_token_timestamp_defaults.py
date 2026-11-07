"""add auth token timestamp defaults

Revision ID: 20260726_0026
Revises: 20260726_0025
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260726_0026"
down_revision: str | None = "20260726_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("password_action_tokens", "refresh_tokens"):
        op.alter_column(table_name, "created_at", server_default=sa.text("now()"))
        op.alter_column(table_name, "updated_at", server_default=sa.text("now()"))


def downgrade() -> None:
    for table_name in ("password_action_tokens", "refresh_tokens"):
        op.alter_column(table_name, "updated_at", server_default=None)
        op.alter_column(table_name, "created_at", server_default=None)
