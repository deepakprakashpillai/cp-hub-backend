from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.batch_schedule_days.models import BatchScheduleDay
from app.modules.bookings._shared import _BookingShared
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import (
    AdminBatchClassReschedule,
    BatchBookingReschedule,
    OneOnOneBookingReschedule,
)
from app.modules.classes.models import ClassSession
from app.modules.teachers.models import Teacher
from app.shared.enums import (
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


class BookingRescheduleService(_BookingShared):
    async def admin_reschedule_batch_class_session(
        self,
        class_session_id: UUID,
        reschedule_in: AdminBatchClassReschedule,
    ) -> list[Booking]:
        await self._get_optional_user(reschedule_in.actor_user_id)
        class_session = await self._get_class_session_for_update(class_session_id)
        if class_session.program_type != StudentProgramType.BATCH:
            raise ConflictError("Class session is not a batch class")
        if class_session.status == ClassSessionStatus.CANCELLED:
            raise ConflictError("Cancelled class sessions cannot be rescheduled")
        if class_session.status == ClassSessionStatus.COMPLETED:
            raise ConflictError("Completed class sessions cannot be rescheduled")

        now = utc_now()
        if _normalize_utc_datetime(class_session.starts_at) <= now:
            raise ConflictError("Started class sessions cannot be rescheduled")
        if reschedule_in.starts_at <= now:
            raise ConflictError("Rescheduled class must start in the future")
        if class_session.batch_schedule_day_id is not None:
            batch_day = await self.session.get(
                BatchScheduleDay,
                class_session.batch_schedule_day_id,
            )
            if batch_day is None:
                raise NotFoundError("Batch schedule day not found")
            if reschedule_in.starts_at.date() != batch_day.schedule_date:
                raise ConflictError("Batch-day options must remain on their UTC schedule date")

        teacher_id = (
            reschedule_in.teacher_id
            if "teacher_id" in reschedule_in.model_fields_set
            else class_session.teacher_id
        )
        batch_slot = (
            reschedule_in.batch_slot
            if "batch_slot" in reschedule_in.model_fields_set
            else class_session.batch_slot
        )
        capacity = (
            reschedule_in.capacity
            if "capacity" in reschedule_in.model_fields_set
            else class_session.capacity
        )
        if batch_slot is None and class_session.display_label is None:
            raise BadRequestError("batch_slot cannot be null")
        if capacity is None:
            raise BadRequestError("capacity cannot be null")

        if teacher_id is not None:
            teacher = await self.session.get(Teacher, teacher_id)
            if teacher is None:
                raise NotFoundError("Teacher not found")
            teacher_overlap = await self.session.scalar(
                select(ClassSession.id).where(
                    ClassSession.id != class_session.id,
                    ClassSession.teacher_id == teacher_id,
                    ClassSession.status != ClassSessionStatus.CANCELLED,
                    ClassSession.starts_at < reschedule_in.ends_at,
                    ClassSession.ends_at > reschedule_in.starts_at,
                )
            )
            if teacher_overlap is not None:
                raise ConflictError("Teacher already has an overlapping class session")

        group_overlap = await self.session.scalar(
            select(ClassSession.id).where(
                ClassSession.id != class_session.id,
                ClassSession.batch_group_id == class_session.batch_group_id,
                ClassSession.status != ClassSessionStatus.CANCELLED,
                ClassSession.starts_at < reschedule_in.ends_at,
                ClassSession.ends_at > reschedule_in.starts_at,
            )
        )
        if group_overlap is not None:
            raise ConflictError("Batch group already has an overlapping class session")

        active_bookings = list(
            await self.session.scalars(
                select(Booking)
                .where(
                    Booking.class_session_id == class_session.id,
                    Booking.status == BookingStatus.BOOKED,
                )
                .order_by(Booking.id.asc())
                .with_for_update()
            )
        )
        if capacity < len(active_bookings):
            raise ConflictError("Capacity cannot be below the active booking count")

        day_start = datetime.combine(reschedule_in.starts_at.date(), time.min, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        for booking in active_bookings:
            daily_conflict = await self.session.scalar(
                select(Booking.id)
                .join(ClassSession, Booking.class_session_id == ClassSession.id)
                .where(
                    Booking.student_id == booking.student_id,
                    Booking.class_session_id != class_session.id,
                    Booking.status != BookingStatus.CANCELLED,
                    ClassSession.status != ClassSessionStatus.CANCELLED,
                    ClassSession.starts_at >= day_start,
                    ClassSession.starts_at < day_end,
                )
            )
            if daily_conflict is not None:
                raise ConflictError("A booked student already has an active class on this day")

        old_timing = {
            "class_session_id": str(class_session.id),
            "starts_at": _normalize_utc_datetime(class_session.starts_at).isoformat(),
            "ends_at": _normalize_utc_datetime(class_session.ends_at).isoformat(),
            "teacher_id": str(class_session.teacher_id) if class_session.teacher_id else None,
            "batch_slot": class_session.batch_slot.value if class_session.batch_slot else None,
            "capacity": class_session.capacity,
        }
        new_timing = {
            "class_session_id": str(class_session.id),
            "starts_at": reschedule_in.starts_at.isoformat(),
            "ends_at": reschedule_in.ends_at.isoformat(),
            "teacher_id": str(teacher_id) if teacher_id else None,
            "batch_slot": batch_slot.value if batch_slot else None,
            "capacity": capacity,
        }
        reason = reschedule_in.reason or RESCHEDULE_REASON
        for booking in active_bookings:
            self._add_booking_event(
                booking_id=booking.id,
                event_type=BookingEventType.RESCHEDULED_FROM,
                actor_user_id=reschedule_in.actor_user_id,
                reason=reason,
                event_metadata={"old": old_timing, "new": new_timing},
            )
            self._add_booking_event(
                booking_id=booking.id,
                event_type=BookingEventType.RESCHEDULED_TO,
                actor_user_id=reschedule_in.actor_user_id,
                reason=reason,
                event_metadata={"old": old_timing, "new": new_timing},
            )

        class_session.starts_at = reschedule_in.starts_at
        class_session.ends_at = reschedule_in.ends_at
        class_session.teacher_id = teacher_id
        class_session.batch_slot = batch_slot
        class_session.capacity = capacity
        for booking in active_bookings:
            student = await self._get_student(booking.student_id)
            await self._emit_booking_created_notification(
                booking=booking,
                student=student,
                class_session=class_session,
                event_type=BookingEventType.RESCHEDULED_TO,
                actor_user_id=reschedule_in.actor_user_id,
            )
        await self.session.commit()
        await self.session.refresh(class_session)
        for booking in active_bookings:
            await self.session.refresh(booking)
        return active_bookings

    async def reschedule_one_on_one_booking(
        self,
        booking_id: UUID,
        reschedule_in: OneOnOneBookingReschedule,
    ) -> Booking:
        return await self._reschedule_one_on_one_booking(
            booking_id=booking_id,
            reschedule_in=reschedule_in,
            enforce_student_cutoff=True,
        )

    async def admin_reschedule_one_on_one_booking(
        self,
        booking_id: UUID,
        reschedule_in: OneOnOneBookingReschedule,
    ) -> Booking:
        return await self._reschedule_one_on_one_booking(
            booking_id=booking_id,
            reschedule_in=reschedule_in,
            enforce_student_cutoff=False,
        )

    async def reschedule_batch_booking(
        self,
        booking_id: UUID,
        reschedule_in: BatchBookingReschedule,
    ) -> Booking:
        return await self._reschedule_batch_booking(
            booking_id=booking_id,
            reschedule_in=reschedule_in,
            enforce_student_cutoff=True,
        )

    async def admin_reschedule_batch_booking(
        self,
        booking_id: UUID,
        reschedule_in: BatchBookingReschedule,
    ) -> Booking:
        return await self._reschedule_batch_booking(
            booking_id=booking_id,
            reschedule_in=reschedule_in,
            enforce_student_cutoff=False,
        )


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
