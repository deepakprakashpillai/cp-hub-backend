from datetime import datetime, time
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Time, Uuid, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.enums import (
    AvailabilitySlotSource,
    AvailabilitySlotStatus,
    DayOfWeek,
    enum_values,
)


class TeacherAvailabilityRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teacher_availability_rules"

    teacher_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("teachers.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    day_of_week: Mapped[DayOfWeek] = mapped_column(
        Enum(DayOfWeek, name="day_of_week", values_callable=enum_values, validate_strings=True),
        nullable=False,
    )
    start_time_utc: Mapped[time] = mapped_column(Time, nullable=False)
    end_time_utc: Mapped[time] = mapped_column(Time, nullable=False)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )


class TeacherAvailabilitySlot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teacher_availability_slots"
    __table_args__ = (
        Index(
            "uq_active_teacher_availability_slot_time",
            "teacher_id",
            "starts_at",
            "ends_at",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
        ),
    )

    teacher_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("teachers.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    rule_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("teacher_availability_rules.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    source: Mapped[AvailabilitySlotSource] = mapped_column(
        Enum(
            AvailabilitySlotSource,
            name="availability_slot_source",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[AvailabilitySlotStatus] = mapped_column(
        Enum(
            AvailabilitySlotStatus,
            name="availability_slot_status",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
