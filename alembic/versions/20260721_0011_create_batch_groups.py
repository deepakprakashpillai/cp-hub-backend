"""create batch groups

Revision ID: 20260721_0011
Revises: 20260720_0010
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260721_0011"
down_revision: str | None = "20260720_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_CLASS_SESSION_SHAPE_CHECK = """
(
    program_type = 'one_on_one'
    and teacher_id is not null
    and teacher_availability_slot_id is not null
    and batch_slot is null
    and capacity = 1
)
or
(
    program_type = 'batch'
    and teacher_availability_slot_id is null
    and batch_slot is not null
)
"""

NEW_CLASS_SESSION_SHAPE_CHECK = """
(
    program_type = 'one_on_one'
    and teacher_id is not null
    and teacher_availability_slot_id is not null
    and batch_group_id is null
    and batch_slot is null
    and capacity = 1
)
or
(
    program_type = 'batch'
    and teacher_availability_slot_id is null
    and batch_group_id is not null
    and batch_slot is not null
)
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "batch_groups",
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("default_capacity", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
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
            "default_capacity > 0",
            name="ck_batch_groups_default_capacity_positive",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_active_batch_groups_name",
        "batch_groups",
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_active is true"),
    )

    op.create_table(
        "student_batch_memberships",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("batch_group_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("assigned_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(length=1000), nullable=True),
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
            """
            (is_active is true and ended_at is null)
            or
            (is_active is false and ended_at is not null)
            """,
            name="ck_student_batch_memberships_active_end_state",
        ),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["batch_group_id"], ["batch_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_student_batch_memberships_assigned_by_user_id"),
        "student_batch_memberships",
        ["assigned_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_batch_memberships_batch_group_id"),
        "student_batch_memberships",
        ["batch_group_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_batch_memberships_student_id"),
        "student_batch_memberships",
        ["student_id"],
        unique=False,
    )
    op.create_index(
        "uq_active_student_batch_membership",
        "student_batch_memberships",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("is_active is true"),
    )

    op.add_column("class_sessions", sa.Column("batch_group_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_class_sessions_batch_group_id_batch_groups"),
        "class_sessions",
        "batch_groups",
        ["batch_group_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_class_sessions_batch_group_id"),
        "class_sessions",
        ["batch_group_id"],
        unique=False,
    )

    op.drop_constraint(
        "ck_class_sessions_program_shape",
        "class_sessions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_class_sessions_program_shape",
        "class_sessions",
        NEW_CLASS_SESSION_SHAPE_CHECK,
    )
    op.execute(
        """
        ALTER TABLE class_sessions
        ADD CONSTRAINT ex_class_sessions_batch_group_time_overlap
        EXCLUDE USING gist (
            batch_group_id WITH =,
            tstzrange(starts_at, ends_at, '[)') WITH &&
        )
        WHERE (batch_group_id IS NOT NULL AND status <> 'cancelled')
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE class_sessions DROP CONSTRAINT ex_class_sessions_batch_group_time_overlap"
    )
    op.drop_constraint(
        "ck_class_sessions_program_shape",
        "class_sessions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_class_sessions_program_shape",
        "class_sessions",
        OLD_CLASS_SESSION_SHAPE_CHECK,
    )
    op.drop_index(op.f("ix_class_sessions_batch_group_id"), table_name="class_sessions")
    op.drop_constraint(
        op.f("fk_class_sessions_batch_group_id_batch_groups"),
        "class_sessions",
        type_="foreignkey",
    )
    op.drop_column("class_sessions", "batch_group_id")

    op.drop_index(
        "uq_active_student_batch_membership",
        table_name="student_batch_memberships",
    )
    op.drop_index(
        op.f("ix_student_batch_memberships_student_id"),
        table_name="student_batch_memberships",
    )
    op.drop_index(
        op.f("ix_student_batch_memberships_batch_group_id"),
        table_name="student_batch_memberships",
    )
    op.drop_index(
        op.f("ix_student_batch_memberships_assigned_by_user_id"),
        table_name="student_batch_memberships",
    )
    op.drop_table("student_batch_memberships")

    op.drop_index("uq_active_batch_groups_name", table_name="batch_groups")
    op.drop_table("batch_groups")
