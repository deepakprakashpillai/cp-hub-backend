from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.enums import BatchScheduleDayStatus, enum_values


class BatchScheduleDay(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "batch_schedule_days"
    __table_args__ = (
        Index(
            "uq_batch_schedule_days_group_date",
            "batch_group_id",
            "schedule_date",
            unique=True,
        ),
    )

    batch_group_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("batch_groups.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    schedule_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[BatchScheduleDayStatus] = mapped_column(
        Enum(
            BatchScheduleDayStatus,
            name="batch_schedule_day_status",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=BatchScheduleDayStatus.SCHEDULED,
        server_default=BatchScheduleDayStatus.SCHEDULED.value,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    cancel_reason: Mapped[str | None] = mapped_column(String(1000))


class BatchScheduleDayEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "batch_schedule_day_events"

    batch_schedule_day_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("batch_schedule_days.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    event_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class BatchScheduleDefaults(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "batch_schedule_defaults"
    __table_args__ = (
        CheckConstraint(
            "default_option_count > 0 and default_option_count <= 8",
            name="ck_batch_schedule_defaults_option_count",
        ),
        CheckConstraint(
            "capacity_strategy in ('batch_group_default', 'fixed')",
            name="ck_batch_schedule_defaults_capacity_strategy",
        ),
        CheckConstraint(
            """
            (capacity_strategy = 'batch_group_default' and fixed_capacity is null)
            or
            (capacity_strategy = 'fixed' and fixed_capacity > 0)
            """,
            name="ck_batch_schedule_defaults_capacity",
        ),
        CheckConstraint("timezone = 'UTC'", name="ck_batch_schedule_defaults_timezone_utc"),
    )

    timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="UTC",
        server_default="UTC",
    )
    default_option_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default="3",
    )
    default_teacher_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("teachers.id", ondelete="SET NULL"),
        nullable=True,
    )
    capacity_strategy: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="batch_group_default",
        server_default="batch_group_default",
    )
    fixed_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    option_templates: Mapped[list[dict]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
