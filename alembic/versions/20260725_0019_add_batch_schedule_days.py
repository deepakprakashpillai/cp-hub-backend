"""add batch schedule days

Revision ID: 20260725_0019
Revises: 20260724_0018
Create Date: 2026-07-25
"""

from collections.abc import Sequence
from uuid import UUID, uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20260725_0019"
down_revision: str | None = "20260724_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULTS_ID = UUID("00000000-0000-0000-0000-000000000001")

NEW_CLASS_SESSION_SHAPE_CHECK = """
(
    program_type = 'one_on_one'
    and teacher_id is not null
    and teacher_availability_slot_id is not null
    and batch_group_id is null
    and batch_slot is null
    and display_label is null
    and batch_schedule_day_id is null
    and capacity = 1
)
or
(
    program_type = 'batch'
    and teacher_availability_slot_id is null
    and batch_group_id is not null
    and (batch_slot is not null or display_label is not null)
)
"""

OLD_CLASS_SESSION_SHAPE_CHECK = """
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
    op.execute("ALTER TYPE booking_event_type ADD VALUE IF NOT EXISTS 'selected_by_student'")
    op.execute("ALTER TYPE booking_event_type ADD VALUE IF NOT EXISTS 'assigned_by_admin'")
    op.execute("ALTER TYPE booking_event_type ADD VALUE IF NOT EXISTS 'moved_by_admin'")
    op.execute("ALTER TYPE booking_event_type ADD VALUE IF NOT EXISTS 'removed_by_admin'")

    op.create_table(
        "batch_schedule_days",
        sa.Column("batch_group_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_date", sa.Date(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["batch_group_id"],
            ["batch_groups.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_batch_schedule_days_group_date",
        "batch_schedule_days",
        ["batch_group_id", "schedule_date"],
        unique=True,
    )
    op.create_index(
        op.f("ix_batch_schedule_days_batch_group_id"),
        "batch_schedule_days",
        ["batch_group_id"],
    )
    op.create_index(
        op.f("ix_batch_schedule_days_schedule_date"),
        "batch_schedule_days",
        ["schedule_date"],
    )

    op.create_table(
        "batch_schedule_defaults",
        sa.Column("timezone", sa.String(length=50), server_default="UTC", nullable=False),
        sa.Column("default_option_count", sa.Integer(), server_default="3", nullable=False),
        sa.Column("default_teacher_id", sa.Uuid(), nullable=True),
        sa.Column(
            "capacity_strategy",
            sa.String(length=30),
            server_default="batch_group_default",
            nullable=False,
        ),
        sa.Column("fixed_capacity", sa.Integer(), nullable=True),
        sa.Column(
            "option_templates",
            sa.JSON(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
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
            "default_option_count > 0 and default_option_count <= 8",
            name="ck_batch_schedule_defaults_option_count",
        ),
        sa.CheckConstraint(
            "capacity_strategy in ('batch_group_default', 'fixed')",
            name="ck_batch_schedule_defaults_capacity_strategy",
        ),
        sa.CheckConstraint(
            """
            (capacity_strategy = 'batch_group_default' and fixed_capacity is null)
            or
            (capacity_strategy = 'fixed' and fixed_capacity > 0)
            """,
            name="ck_batch_schedule_defaults_capacity",
        ),
        sa.CheckConstraint(
            "timezone = 'UTC'",
            name="ck_batch_schedule_defaults_timezone_utc",
        ),
        sa.ForeignKeyConstraint(
            ["default_teacher_id"],
            ["teachers.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    defaults_table = sa.table(
        "batch_schedule_defaults",
        sa.column("id", sa.Uuid()),
        sa.column("timezone", sa.String()),
        sa.column("default_option_count", sa.Integer()),
        sa.column("capacity_strategy", sa.String()),
        sa.column("option_templates", sa.JSON()),
    )
    op.bulk_insert(
        defaults_table,
        [
            {
                "id": DEFAULTS_ID,
                "timezone": "UTC",
                "default_option_count": 3,
                "capacity_strategy": "batch_group_default",
                "option_templates": [
                    {
                        "display_label": "Morning",
                        "start_time_utc": "08:00:00",
                        "duration_minutes": 60,
                    },
                    {
                        "display_label": "Noon",
                        "start_time_utc": "12:00:00",
                        "duration_minutes": 60,
                    },
                    {
                        "display_label": "Evening",
                        "start_time_utc": "18:00:00",
                        "duration_minutes": 60,
                    },
                ],
            }
        ],
    )

    op.add_column(
        "class_sessions",
        sa.Column("batch_schedule_day_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "class_sessions",
        sa.Column("display_label", sa.String(length=150), nullable=True),
    )
    op.add_column(
        "class_sessions",
        sa.Column("option_order", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_class_sessions_batch_schedule_day_id_batch_schedule_days"),
        "class_sessions",
        "batch_schedule_days",
        ["batch_schedule_day_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_class_sessions_batch_schedule_day_id"),
        "class_sessions",
        ["batch_schedule_day_id"],
    )
    op.create_index(
        "uq_class_sessions_batch_day_option_order",
        "class_sessions",
        ["batch_schedule_day_id", "option_order"],
        unique=True,
        postgresql_where=sa.text("batch_schedule_day_id is not null"),
    )

    connection = op.get_bind()
    legacy_days = connection.execute(
        sa.text(
            """
            SELECT DISTINCT batch_group_id, (starts_at AT TIME ZONE 'UTC')::date AS schedule_date
            FROM class_sessions
            WHERE program_type = 'batch' AND batch_group_id IS NOT NULL
            """
        )
    ).mappings()
    for row in legacy_days:
        day_id = uuid4()
        connection.execute(
            sa.text(
                """
                INSERT INTO batch_schedule_days (id, batch_group_id, schedule_date)
                VALUES (:id, :batch_group_id, :schedule_date)
                """
            ),
            {
                "id": day_id,
                "batch_group_id": row["batch_group_id"],
                "schedule_date": row["schedule_date"],
            },
        )
        connection.execute(
            sa.text(
                """
                WITH ordered AS (
                    SELECT id,
                           row_number() OVER (ORDER BY starts_at, id) AS option_order
                    FROM class_sessions
                    WHERE batch_group_id = :batch_group_id
                      AND (starts_at AT TIME ZONE 'UTC')::date = :schedule_date
                )
                UPDATE class_sessions AS cs
                SET batch_schedule_day_id = :day_id,
                    display_label = initcap(replace(cs.batch_slot::text, '_', ' ')),
                    option_order = ordered.option_order
                FROM ordered
                WHERE cs.id = ordered.id
                """
            ),
            {
                "day_id": day_id,
                "batch_group_id": row["batch_group_id"],
                "schedule_date": row["schedule_date"],
            },
        )

    op.drop_constraint("ck_class_sessions_program_shape", "class_sessions", type_="check")
    op.create_check_constraint(
        "ck_class_sessions_program_shape",
        "class_sessions",
        NEW_CLASS_SESSION_SHAPE_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint("ck_class_sessions_program_shape", "class_sessions", type_="check")
    op.create_check_constraint(
        "ck_class_sessions_program_shape",
        "class_sessions",
        OLD_CLASS_SESSION_SHAPE_CHECK,
    )
    op.drop_index(
        "uq_class_sessions_batch_day_option_order",
        table_name="class_sessions",
    )
    op.drop_index(
        op.f("ix_class_sessions_batch_schedule_day_id"),
        table_name="class_sessions",
    )
    op.drop_constraint(
        op.f("fk_class_sessions_batch_schedule_day_id_batch_schedule_days"),
        "class_sessions",
        type_="foreignkey",
    )
    op.drop_column("class_sessions", "option_order")
    op.drop_column("class_sessions", "display_label")
    op.drop_column("class_sessions", "batch_schedule_day_id")
    op.drop_table("batch_schedule_defaults")
    op.drop_index(
        op.f("ix_batch_schedule_days_schedule_date"),
        table_name="batch_schedule_days",
    )
    op.drop_index(
        op.f("ix_batch_schedule_days_batch_group_id"),
        table_name="batch_schedule_days",
    )
    op.drop_index(
        "uq_batch_schedule_days_group_date",
        table_name="batch_schedule_days",
    )
    op.drop_table("batch_schedule_days")
