from uuid import UUID

from sqlalchemy import Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.enums import BookingNoteVisibility, enum_values


class BookingNote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "booking_notes"

    booking_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    class_session_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("class_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    student_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("students.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    teacher_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("teachers.id"),
        index=True,
        nullable=False,
    )
    note: Mapped[str] = mapped_column(String(2000), nullable=False)
    visibility: Mapped[BookingNoteVisibility] = mapped_column(
        Enum(
            BookingNoteVisibility,
            name="booking_note_visibility",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=BookingNoteVisibility.ADMIN_ONLY,
        server_default=BookingNoteVisibility.ADMIN_ONLY.value,
    )
