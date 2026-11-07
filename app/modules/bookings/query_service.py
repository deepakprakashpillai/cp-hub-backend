from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_scalars
from app.modules.bookings._shared import _BookingShared
from app.modules.bookings.models import Booking, BookingEvent
from app.modules.classes.models import ClassSession
from app.shared.enums import (
    BookingStatus,
)

BATCH_BOOKING_CLOSES_BEFORE_START = timedelta(hours=3)
STUDENT_BOOKING_CHANGE_CUTOFF = timedelta(hours=24)
BOOKED_REASON = "booked"
STUDENT_CANCEL_REASON = "cancelled by student"
ADMIN_CANCEL_REASON = "cancelled by admin"
RESCHEDULE_REASON = "rescheduled"
EMPTY_CLASS_REASON = "empty class"
ATTENDED_REASON = "present"
MISSED_REASON = "absent"
MANUAL_ADD_REASON = "manually added by admin"
CLASS_CANCEL_REASON = "class cancelled by admin"
TEACHER_CLASS_CANCEL_REASON = "class cancelled by teacher"


class BookingQueryService(_BookingShared):
    async def list_bookings(
        self,
        pagination: PaginationParams,
        student_id: UUID | None = None,
        class_session_id: UUID | None = None,
        status: BookingStatus | None = None,
        teacher_id: UUID | None = None,
        starts_from: datetime | None = None,
        starts_to: datetime | None = None,
    ) -> Page:
        statement = select(Booking).order_by(Booking.created_at.desc())
        if teacher_id is not None or starts_from is not None or starts_to is not None:
            statement = statement.join(ClassSession, Booking.class_session_id == ClassSession.id)
        if student_id is not None:
            statement = statement.where(Booking.student_id == student_id)
        if class_session_id is not None:
            statement = statement.where(Booking.class_session_id == class_session_id)
        if status is not None:
            statement = statement.where(Booking.status == status)
        if teacher_id is not None:
            statement = statement.where(ClassSession.teacher_id == teacher_id)
        if starts_from is not None:
            statement = statement.where(ClassSession.starts_at >= starts_from)
        if starts_to is not None:
            statement = statement.where(ClassSession.starts_at <= starts_to)

        return await paginate_scalars(self.session, statement, pagination)

    async def get_booking(self, booking_id: UUID) -> Booking:
        booking = await self.session.get(Booking, booking_id)
        if booking is None:
            raise NotFoundError("Booking not found")
        return booking

    async def list_booking_events(
        self,
        booking_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        await self.get_booking(booking_id)
        statement = (
            select(BookingEvent)
            .where(BookingEvent.booking_id == booking_id)
            .order_by(BookingEvent.created_at.asc())
        )
        return await paginate_scalars(self.session, statement, pagination)
