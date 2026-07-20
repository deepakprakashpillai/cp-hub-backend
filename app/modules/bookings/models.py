from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.enums import BookingStatus, enum_values


class Booking(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        Index(
            "uq_active_booking_student_class_session",
            "student_id",
            "class_session_id",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
        ),
    )

    student_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("students.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    class_session_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("class_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[BookingStatus] = mapped_column(
        Enum(
            BookingStatus,
            name="booking_status",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=BookingStatus.BOOKED,
        server_default=BookingStatus.BOOKED.value,
    )
    booked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
