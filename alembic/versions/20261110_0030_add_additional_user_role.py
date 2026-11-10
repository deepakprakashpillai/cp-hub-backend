"""Allow an admin and teacher role on the same account.

Revision ID: 20261110_0030
Revises: 20260729_0029
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261110_0030"
down_revision = "20260729_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "additional_role",
            postgresql.ENUM(name="user_role", create_type=False),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_users_additional_role",
        "users",
        "additional_role IS NULL OR "
        "(role = 'admin' AND additional_role = 'teacher') OR "
        "(role = 'teacher' AND additional_role = 'admin')",
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM users WHERE additional_role IS NOT NULL) "
        "THEN RAISE EXCEPTION 'Remove additional roles before downgrading'; END IF; END $$"
    )
    op.drop_constraint("ck_users_additional_role", "users", type_="check")
    op.drop_column("users", "additional_role")
