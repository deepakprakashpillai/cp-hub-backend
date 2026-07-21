from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.enums import BookingEventType, BookingStatus, enum_values


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


class BookingEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "booking_events"

    booking_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    event_type: Mapped[BookingEventType] = mapped_column(
        Enum(
            BookingEventType,
            name="booking_event_type",
            values_callable=enum_values,
            validate_strings=True,
        ),
        index=True,
        nullable=False,
    )
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
