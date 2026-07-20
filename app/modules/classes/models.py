from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.enums import BatchSlot, ClassSessionStatus, StudentProgramType, enum_values


class ClassSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "class_sessions"
    __table_args__ = (
        CheckConstraint("starts_at < ends_at", name="ck_class_sessions_time_range_valid"),
        CheckConstraint("capacity > 0", name="ck_class_sessions_capacity_positive"),
        CheckConstraint(
            """
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
            """,
            name="ck_class_sessions_program_shape",
        ),
        Index(
            "uq_class_sessions_teacher_availability_slot_id",
            "teacher_availability_slot_id",
            unique=True,
            postgresql_where=text(
                "teacher_availability_slot_id is not null and status <> 'cancelled'"
            ),
        ),
    )

    teacher_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("teachers.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    teacher_availability_slot_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("teacher_availability_slots.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    program_type: Mapped[StudentProgramType] = mapped_column(
        Enum(
            StudentProgramType,
            name="student_program_type",
            values_callable=enum_values,
            validate_strings=True,
        ),
        index=True,
        nullable=False,
    )
    batch_slot: Mapped[BatchSlot | None] = mapped_column(
        Enum(
            BatchSlot,
            name="batch_slot",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=True,
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ClassSessionStatus] = mapped_column(
        Enum(
            ClassSessionStatus,
            name="class_session_status",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=ClassSessionStatus.SCHEDULED,
        server_default=ClassSessionStatus.SCHEDULED.value,
    )
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
