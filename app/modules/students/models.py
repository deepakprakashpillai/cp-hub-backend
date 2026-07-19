from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.enums import StudentProgramType, StudentStatus, enum_values


class Student(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "students"

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    program_type: Mapped[StudentProgramType] = mapped_column(
        Enum(
            StudentProgramType,
            name="student_program_type",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    status: Mapped[StudentStatus] = mapped_column(
        Enum(
            StudentStatus,
            name="student_status",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=StudentStatus.ENROLLED,
        server_default=StudentStatus.ENROLLED.value,
    )
    access_starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    access_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class StudentProgramChange(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_program_changes"

    student_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("students.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    old_program_type: Mapped[StudentProgramType] = mapped_column(
        Enum(
            StudentProgramType,
            name="student_program_type",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    new_program_type: Mapped[StudentProgramType] = mapped_column(
        Enum(
            StudentProgramType,
            name="student_program_type",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    changed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
