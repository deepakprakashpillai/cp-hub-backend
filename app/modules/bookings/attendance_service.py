from datetime import timedelta
from uuid import UUID

from app.core.exceptions import ConflictError
from app.modules.bookings._shared import _BookingShared
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import (
    AdminAddStudentToClass,
    BookingAttendanceMark,
    ClassAttendanceMark,
)
from app.shared.enums import (
    BookingEventType,
    BookingStatus,
    ClassSessionStatus,
)
from app.shared.utils import utc_now

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


class BookingAttendanceService(_BookingShared):
    async def mark_booking_attendance(
        self,
        booking_id: UUID,
        attendance_in: BookingAttendanceMark,
    ) -> Booking:
        await self._get_optional_user(attendance_in.actor_user_id)
        booking = await self._get_booking_for_update(booking_id)
        class_session = await self._get_class_session_for_update(booking.class_session_id)
        now = utc_now()

        await self._mark_booking_attendance(
            booking=booking,
            class_session=class_session,
            status=attendance_in.status,
            actor_user_id=attendance_in.actor_user_id,
            reason=attendance_in.reason or _default_attendance_reason(attendance_in.status),
            now=now,
        )
        await self._complete_class_session_if_attendance_marked(class_session)

        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    async def mark_class_attendance(
        self,
        class_session_id: UUID,
        attendance_in: ClassAttendanceMark,
    ) -> list[Booking]:
        await self._get_optional_user(attendance_in.actor_user_id)
        class_session = await self._get_class_session_for_update(class_session_id)
        now = utc_now()

        bookings: list[Booking] = []
        for record in attendance_in.records:
            booking = await self._get_booking_for_update(record.booking_id)
            if booking.class_session_id != class_session.id:
                raise ConflictError("Attendance booking does not belong to this class session")

            await self._mark_booking_attendance(
                booking=booking,
                class_session=class_session,
                status=record.status,
                actor_user_id=attendance_in.actor_user_id,
                reason=record.reason or _default_attendance_reason(record.status),
                now=now,
            )
            bookings.append(booking)

        await self._complete_class_session_if_attendance_marked(class_session)

        await self.session.commit()
        for booking in bookings:
            await self.session.refresh(booking)
        return bookings

    async def admin_add_student_to_class(
        self,
        class_session_id: UUID,
        add_in: AdminAddStudentToClass,
    ) -> Booking:
        await self._get_optional_user(add_in.actor_user_id)
        now = utc_now()
        student = await self._get_student(add_in.student_id)
        self._ensure_student_has_active_access(student=student, now=now)

        class_session = await self._get_class_session_for_update(class_session_id)
        if class_session.status != ClassSessionStatus.SCHEDULED:
            raise ConflictError("Students can only be manually added to scheduled classes")

        await self._ensure_no_active_booking_for_class_session(
            student_id=student.id,
            class_session_id=class_session.id,
        )
        await self._ensure_no_active_class_on_day(
            student_id=student.id,
            class_starts_at=class_session.starts_at,
        )
        await self._ensure_class_session_capacity_available(class_session)

        booking = Booking(
            student_id=student.id,
            class_session_id=class_session.id,
            status=BookingStatus.BOOKED,
            booked_at=now,
        )
        self.session.add(booking)
        await self.session.flush()
        self._add_booking_event(
            booking_id=booking.id,
            event_type=BookingEventType.MANUALLY_ADDED_BY_ADMIN,
            actor_user_id=add_in.actor_user_id,
            reason=add_in.reason or MANUAL_ADD_REASON,
            event_metadata={"class_session_id": str(class_session.id)},
        )

        await self.session.commit()
        await self.session.refresh(booking)
        return booking


def _default_attendance_reason(status: BookingStatus) -> str:
    if status == BookingStatus.ATTENDED:
        return ATTENDED_REASON
    return MISSED_REASON
