from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.enums import StudentAccessGrantType, enum_values


class StudentAccessGrant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_access_grants"

    student_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("students.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    package_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("packages.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    grant_type: Mapped[StudentAccessGrantType] = mapped_column(
        Enum(
            StudentAccessGrantType,
            name="student_access_grant_type",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    access_starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    access_ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
