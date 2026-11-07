from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import ConflictError
from app.modules.bookings._shared import _BookingShared
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import (
    BookingActionRequest,
)
from app.modules.classes.models import ClassSession
from app.modules.schedules.models import TeacherAvailabilitySlot
from app.modules.students.models import Student
from app.shared.enums import (
    AvailabilitySlotStatus,
    BookingEventType,
    BookingStatus,
    ClassSessionStatus,
    StudentProgramType,
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


class BookingCancellationService(_BookingShared):
    async def cancel_booking(
        self,
        booking_id: UUID,
        cancel_in: BookingActionRequest,
    ) -> Booking:
        return await self._cancel_booking(
            booking_id=booking_id,
            actor_user_id=cancel_in.actor_user_id,
            reason=cancel_in.reason or STUDENT_CANCEL_REASON,
            event_type=BookingEventType.CANCELLED_BY_STUDENT,
            enforce_student_cutoff=True,
            commit=True,
        )

    async def admin_cancel_booking(
        self,
        booking_id: UUID,
        cancel_in: BookingActionRequest,
    ) -> Booking:
        return await self._cancel_booking(
            booking_id=booking_id,
            actor_user_id=cancel_in.actor_user_id,
            reason=cancel_in.reason or ADMIN_CANCEL_REASON,
            event_type=BookingEventType.CANCELLED_BY_ADMIN,
            enforce_student_cutoff=False,
            commit=True,
        )

    async def admin_cancel_class_session(
        self,
        class_session_id: UUID,
        cancel_in: BookingActionRequest,
    ) -> ClassSession:
        await self._get_optional_user(cancel_in.actor_user_id)
        class_session = await self._get_class_session_for_update(class_session_id)
        if class_session.status == ClassSessionStatus.CANCELLED:
            raise ConflictError("Class session is already cancelled")
        if class_session.status == ClassSessionStatus.COMPLETED:
            raise ConflictError("Completed class sessions cannot be cancelled")

        now = utc_now()
        reason = cancel_in.reason or CLASS_CANCEL_REASON
        class_session.status = ClassSessionStatus.CANCELLED

        result = await self.session.scalars(
            select(Booking)
            .where(
                Booking.class_session_id == class_session.id,
                Booking.status == BookingStatus.BOOKED,
            )
            .with_for_update()
        )
        bookings = list(result)
        for booking in bookings:
            booking.status = BookingStatus.CANCELLED
            self._add_booking_event(
                booking_id=booking.id,
                event_type=BookingEventType.CANCELLED_BY_ADMIN,
                actor_user_id=cancel_in.actor_user_id,
                reason=reason,
                event_metadata={"class_session_id": str(class_session.id)},
            )
            student = await self.session.get(Student, booking.student_id)
            if isinstance(student, Student):
                await self._emit_booking_cancelled_notification(
                    booking=booking,
                    student=student,
                    class_session=class_session,
                    event_type=BookingEventType.CANCELLED_BY_ADMIN,
                    actor_user_id=cancel_in.actor_user_id,
                )

        if (
            class_session.program_type == StudentProgramType.ONE_ON_ONE
            and _normalize_utc_datetime(class_session.starts_at) > now
            and class_session.teacher_availability_slot_id is not None
        ):
            slot = await self.session.get(
                TeacherAvailabilitySlot,
                class_session.teacher_availability_slot_id,
            )
            if slot is not None and slot.status == AvailabilitySlotStatus.BOOKED:
                slot.status = AvailabilitySlotStatus.AVAILABLE

        await self.session.commit()
        await self.session.refresh(class_session)
        return class_session

    async def teacher_cancel_batch_class_session(
        self,
        class_session_id: UUID,
        cancel_in: BookingActionRequest,
    ) -> ClassSession:
        """Cancel one future batch-day option on behalf of its assigned teacher."""
        await self._get_optional_user(cancel_in.actor_user_id)
        class_session = await self._get_class_session_for_update(class_session_id)
        if class_session.program_type != StudentProgramType.BATCH:
            raise ConflictError("Class session is not a batch class")
        if class_session.batch_schedule_day_id is None:
            raise ConflictError("Class session is not a batch schedule-day option")
        if class_session.status != ClassSessionStatus.SCHEDULED:
            raise ConflictError("Only scheduled class sessions can be cancelled")
        if _normalize_utc_datetime(class_session.starts_at) <= utc_now():
            raise ConflictError("Started class sessions cannot be cancelled")

        class_session.status = ClassSessionStatus.CANCELLED
        result = await self.session.scalars(
            select(Booking)
            .where(
                Booking.class_session_id == class_session.id,
                Booking.status == BookingStatus.BOOKED,
            )
            .with_for_update()
        )
        reason = cancel_in.reason or TEACHER_CLASS_CANCEL_REASON
        bookings = list(result)
        for booking in bookings:
            booking.status = BookingStatus.CANCELLED
            self._add_booking_event(
                booking_id=booking.id,
                event_type=BookingEventType.CANCELLED_BY_TEACHER,
                actor_user_id=cancel_in.actor_user_id,
                reason=reason,
                event_metadata={"class_session_id": str(class_session.id)},
            )
            student = await self.session.get(Student, booking.student_id)
            if isinstance(student, Student):
                await self._emit_booking_cancelled_notification(
                    booking=booking,
                    student=student,
                    class_session=class_session,
                    event_type=BookingEventType.CANCELLED_BY_TEACHER,
                    actor_user_id=cancel_in.actor_user_id,
                )

        await self.session.commit()
        await self.session.refresh(class_session)
        return class_session

    async def cancel_future_bookings_for_student(
        self,
        student_id: UUID,
        *,
        now: datetime | None = None,
        commit: bool = True,
    ) -> int:
        cancellation_now = _normalize_utc_datetime(now or utc_now())
        result = await self.session.execute(
            select(Booking, ClassSession)
            .join(ClassSession, Booking.class_session_id == ClassSession.id)
            .where(
                Booking.student_id == student_id,
                Booking.status == BookingStatus.BOOKED,
                ClassSession.starts_at > cancellation_now,
            )
        )

        cancelled_count = 0
        for booking, class_session in result.all():
            booking.status = BookingStatus.CANCELLED
            self._add_booking_event(
                booking_id=booking.id,
                event_type=BookingEventType.CANCELLED_BY_ADMIN,
                actor_user_id=None,
                reason="program switch",
                event_metadata={},
            )
            cancelled_count += 1

            if class_session.program_type == StudentProgramType.ONE_ON_ONE:
                class_session.status = ClassSessionStatus.CANCELLED
                if class_session.teacher_availability_slot_id is not None:
                    slot = await self.session.get(
                        TeacherAvailabilitySlot,
                        class_session.teacher_availability_slot_id,
                    )
                    if slot is not None and slot.status == AvailabilitySlotStatus.BOOKED:
                        slot.status = AvailabilitySlotStatus.AVAILABLE

        if commit:
            await self.session.commit()

        return cancelled_count


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
