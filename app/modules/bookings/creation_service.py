from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.batch_schedule_days.models import BatchScheduleDay
from app.modules.bookings._shared import _BookingShared
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import (
    BatchBookingCreate,
    OneOnOneBookingCreate,
)
from app.modules.classes.models import ClassSession
from app.modules.students.models import Student
from app.shared.enums import (
    BatchScheduleDayStatus,
    BookingEventType,
    BookingStatus,
    ClassSessionStatus,
    StudentProgramType,
    StudentStatus,
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


class BookingCreationService(_BookingShared):
    async def create_one_on_one_booking(self, booking_in: OneOnOneBookingCreate) -> Booking:
        now = utc_now()
        return await self._create_one_on_one_booking(
            booking_in=booking_in,
            now=now,
            event_type=BookingEventType.BOOKED,
            reason=BOOKED_REASON,
            actor_user_id=None,
            event_metadata={},
            commit=True,
        )

    async def create_batch_booking(self, booking_in: BatchBookingCreate) -> Booking:
        now = utc_now()
        return await self._create_batch_booking(
            booking_in=booking_in,
            now=now,
            event_type=BookingEventType.BOOKED,
            reason=BOOKED_REASON,
            actor_user_id=None,
            event_metadata={},
            commit=True,
        )

    async def select_batch_day_option(
        self,
        *,
        student_id: UUID,
        batch_schedule_day_id: UUID,
        class_session_id: UUID,
        admin_override: bool,
        actor_user_id: UUID | None,
        reason: str | None,
    ) -> tuple[Booking, UUID | None]:
        if admin_override:
            await self._get_optional_user(actor_user_id)
        student = await self.session.scalar(
            select(Student).where(Student.id == student_id).with_for_update()
        )
        if student is None:
            raise NotFoundError("Student not found")
        if student.program_type != StudentProgramType.BATCH:
            raise ConflictError("Student is not a batch student")
        if student.status != StudentStatus.ACTIVE:
            raise ConflictError("Student is not active")

        day = await self.session.get(BatchScheduleDay, batch_schedule_day_id)
        if day is None:
            raise NotFoundError("Batch schedule day not found")
        if day.status == BatchScheduleDayStatus.CANCELLED:
            raise ConflictError("Batch schedule day is not scheduled")
        membership = await self._get_active_student_batch_membership(student.id)
        if membership.batch_group_id != day.batch_group_id:
            raise ConflictError("Student is not an active member of this batch")
        class_session = await self._get_class_session_for_update(class_session_id)
        if class_session.batch_schedule_day_id != day.id:
            raise ConflictError("Class session is not an option for this batch day")
        if class_session.status != ClassSessionStatus.SCHEDULED:
            raise ConflictError("Batch-day option is not scheduled")
        now = utc_now()
        if class_session.starts_at <= now:
            raise ConflictError("Batch-day option has already started")
        self._ensure_student_access_covers_class(student, class_session.starts_at)

        existing_booking = await self.session.scalar(
            select(Booking)
            .join(ClassSession, Booking.class_session_id == ClassSession.id)
            .where(
                Booking.student_id == student.id,
                Booking.status != BookingStatus.CANCELLED,
                ClassSession.batch_schedule_day_id == day.id,
            )
            .with_for_update()
        )
        if existing_booking is not None and existing_booking.class_session_id == class_session.id:
            raise ConflictError("Student already selected this option")
        if existing_booking is not None and not admin_override:
            raise ConflictError("Student already selected an option for this batch day")

        day_start = datetime.combine(day.schedule_date, time.min, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        daily_conflict_statement = (
            select(Booking.id)
            .join(ClassSession, Booking.class_session_id == ClassSession.id)
            .where(
                Booking.student_id == student.id,
                Booking.status != BookingStatus.CANCELLED,
                ClassSession.status != ClassSessionStatus.CANCELLED,
                ClassSession.starts_at >= day_start,
                ClassSession.starts_at < day_end,
            )
        )
        if existing_booking is not None:
            daily_conflict_statement = daily_conflict_statement.where(
                Booking.id != existing_booking.id
            )
        if await self.session.scalar(daily_conflict_statement) is not None:
            raise ConflictError("Student already has an active class on this UTC date")

        await self._ensure_class_session_capacity_available(class_session)
        moved_from_booking_id = None
        if existing_booking is not None:
            moved_from_booking_id = existing_booking.id
            existing_booking.status = BookingStatus.CANCELLED
            self._add_booking_event(
                booking_id=existing_booking.id,
                event_type=BookingEventType.MOVED_BY_ADMIN,
                actor_user_id=actor_user_id,
                reason=reason or "moved by admin",
                event_metadata={
                    "source": "admin",
                    "batch_schedule_day_id": str(day.id),
                    "from_class_session_id": str(existing_booking.class_session_id),
                    "to_class_session_id": str(class_session.id),
                },
            )
            await self.session.flush()

        booking = Booking(
            student_id=student.id,
            class_session_id=class_session.id,
            status=BookingStatus.BOOKED,
            booked_at=now,
        )
        self.session.add(booking)
        await self.session.flush()
        event_type = (
            BookingEventType.MOVED_BY_ADMIN
            if moved_from_booking_id is not None
            else (
                BookingEventType.ASSIGNED_BY_ADMIN
                if admin_override
                else BookingEventType.SELECTED_BY_STUDENT
            )
        )
        source = "admin" if admin_override else "student"
        self._add_booking_event(
            booking_id=booking.id,
            event_type=event_type,
            actor_user_id=actor_user_id if admin_override else student.user_id,
            reason=reason
            or (
                "moved by admin"
                if moved_from_booking_id is not None
                else "assigned by admin"
                if admin_override
                else "selected by student"
            ),
            event_metadata={
                "source": source,
                "batch_schedule_day_id": str(day.id),
                "class_session_id": str(class_session.id),
                "moved_from_booking_id": (
                    str(moved_from_booking_id) if moved_from_booking_id else None
                ),
            },
        )
        await self.session.commit()
        await self.session.refresh(booking)
        return booking, moved_from_booking_id

    async def remove_batch_day_selection(
        self,
        *,
        student_id: UUID,
        batch_schedule_day_id: UUID,
        actor_user_id: UUID | None,
        reason: str | None,
    ) -> Booking:
        await self._get_optional_user(actor_user_id)
        booking = await self.session.scalar(
            select(Booking)
            .join(ClassSession, Booking.class_session_id == ClassSession.id)
            .where(
                Booking.student_id == student_id,
                Booking.status == BookingStatus.BOOKED,
                ClassSession.batch_schedule_day_id == batch_schedule_day_id,
            )
            .with_for_update()
        )
        if booking is None:
            raise NotFoundError("Active batch-day selection not found")
        booking.status = BookingStatus.CANCELLED
        self._add_booking_event(
            booking_id=booking.id,
            event_type=BookingEventType.REMOVED_BY_ADMIN,
            actor_user_id=actor_user_id,
            reason=reason or "removed by admin",
            event_metadata={
                "source": "admin",
                "batch_schedule_day_id": str(batch_schedule_day_id),
                "class_session_id": str(booking.class_session_id),
            },
        )
        await self.session.commit()
        await self.session.refresh(booking)
        return booking
