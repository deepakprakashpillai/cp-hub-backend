from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_scalars
from app.modules.batch_groups.models import StudentBatchMembership
from app.modules.batch_schedule_days.models import BatchScheduleDay
from app.modules.bookings.models import Booking, BookingEvent
from app.modules.bookings.schemas import (
    AdminAddStudentToClass,
    BatchBookingCreate,
    BatchBookingReschedule,
    BookingActionRequest,
    BookingAttendanceMark,
    ClassAttendanceMark,
    OneOnOneBookingCreate,
    OneOnOneBookingReschedule,
)
from app.modules.classes.models import ClassSession
from app.modules.schedules.models import TeacherAvailabilitySlot
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
from app.modules.users.models import User
from app.shared.enums import (
    AvailabilitySlotStatus,
    BatchScheduleDayStatus,
    BookingEventType,
    BookingStatus,
    ClassSessionStatus,
    StudentProgramType,
    StudentStatus,
)
from app.shared.utils import utc_now

if TYPE_CHECKING:
    from app.modules.admin.schemas import AdminBatchClassReschedule

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


class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
        for booking in result:
            booking.status = BookingStatus.CANCELLED
            self._add_booking_event(
                booking_id=booking.id,
                event_type=BookingEventType.CANCELLED_BY_ADMIN,
                actor_user_id=cancel_in.actor_user_id,
                reason=reason,
                event_metadata={"class_session_id": str(class_session.id)},
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

    async def admin_reschedule_batch_class_session(
        self,
        class_session_id: UUID,
        reschedule_in: "AdminBatchClassReschedule",
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
                raise ConflictError(
                    "Batch-day options must remain on their UTC schedule date"
                )

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

    async def _create_one_on_one_booking(
        self,
        *,
        booking_in: OneOnOneBookingCreate,
        now: datetime,
        event_type: BookingEventType,
        reason: str,
        actor_user_id: UUID | None,
        event_metadata: dict,
        commit: bool,
    ) -> Booking:
        await self._get_optional_user(actor_user_id)
        student = await self._get_student(booking_in.student_id)
        self._ensure_student_can_book(
            student=student,
            expected_program_type=StudentProgramType.ONE_ON_ONE,
            now=now,
        )

        slot = await self._get_teacher_availability_slot_for_update(
            booking_in.teacher_availability_slot_id
        )
        if slot.status != AvailabilitySlotStatus.AVAILABLE:
            raise ConflictError("Teacher availability slot is not available")
        if slot.starts_at <= now:
            raise BadRequestError("Cannot book a past or started slot")

        await self._ensure_no_booked_class_on_day(
            student_id=student.id,
            class_starts_at=slot.starts_at,
        )
        await self._ensure_no_active_session_for_slot(slot.id)

        class_session = ClassSession(
            teacher_id=slot.teacher_id,
            teacher_availability_slot_id=slot.id,
            program_type=StudentProgramType.ONE_ON_ONE,
            batch_slot=None,
            batch_group_id=None,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
            status=ClassSessionStatus.SCHEDULED,
            capacity=1,
        )
        self.session.add(class_session)
        await self.session.flush()

        booking = Booking(
            student_id=student.id,
            class_session_id=class_session.id,
            status=BookingStatus.BOOKED,
            booked_at=now,
        )
        slot.status = AvailabilitySlotStatus.BOOKED
        self.session.add(booking)
        await self.session.flush()
        self._add_booking_event(
            booking_id=booking.id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            reason=reason,
            event_metadata=event_metadata,
        )

        if commit:
            await self.session.commit()
            await self.session.refresh(booking)
        return booking

    async def _create_batch_booking(
        self,
        *,
        booking_in: BatchBookingCreate,
        now: datetime,
        event_type: BookingEventType,
        reason: str,
        actor_user_id: UUID | None,
        event_metadata: dict,
        commit: bool,
    ) -> Booking:
        await self._get_optional_user(actor_user_id)
        student = await self._get_student(booking_in.student_id)
        self._ensure_student_can_book(
            student=student,
            expected_program_type=StudentProgramType.BATCH,
            now=now,
        )

        class_session = await self._get_class_session_for_update(booking_in.class_session_id)
        if class_session.program_type != StudentProgramType.BATCH:
            raise ConflictError("Class session is not a batch session")
        if class_session.batch_group_id is None:
            raise ConflictError("Batch class session is missing batch group")
        active_membership = await self._get_active_student_batch_membership(student.id)
        if active_membership is None:
            raise ConflictError("Student does not have an active batch membership")
        if active_membership.batch_group_id != class_session.batch_group_id:
            raise ConflictError("Student is not assigned to this batch group")
        if class_session.status != ClassSessionStatus.SCHEDULED:
            raise ConflictError("Class session is not scheduled")
        if class_session.starts_at <= now:
            raise BadRequestError("Cannot book a past or started class session")
        if class_session.starts_at - now <= BATCH_BOOKING_CLOSES_BEFORE_START:
            raise ConflictError("Batch booking window is closed")

        await self._ensure_no_booked_class_on_day(
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
            event_type=event_type,
            actor_user_id=actor_user_id,
            reason=reason,
            event_metadata=event_metadata,
        )

        if commit:
            await self.session.commit()
            await self.session.refresh(booking)
        return booking

    async def _cancel_booking(
        self,
        *,
        booking_id: UUID,
        actor_user_id: UUID | None,
        reason: str,
        event_type: BookingEventType,
        enforce_student_cutoff: bool,
        commit: bool,
    ) -> Booking:
        await self._get_optional_user(actor_user_id)
        booking = await self._get_booking_for_update(booking_id)
        class_session = await self._get_class_session_for_update(booking.class_session_id)
        now = utc_now()

        await self._cancel_existing_booking(
            booking=booking,
            class_session=class_session,
            now=now,
            actor_user_id=actor_user_id,
            reason=reason,
            event_type=event_type,
            enforce_student_cutoff=enforce_student_cutoff,
        )

        if commit:
            await self.session.commit()
            await self.session.refresh(booking)
        return booking

    async def _reschedule_one_on_one_booking(
        self,
        *,
        booking_id: UUID,
        reschedule_in: OneOnOneBookingReschedule,
        enforce_student_cutoff: bool,
    ) -> Booking:
        await self._get_optional_user(reschedule_in.actor_user_id)
        booking = await self._get_booking_for_update(booking_id)
        class_session = await self._get_class_session_for_update(booking.class_session_id)
        if class_session.program_type != StudentProgramType.ONE_ON_ONE:
            raise ConflictError("Booking is not for a one-on-one class")

        now = utc_now()
        reason = reschedule_in.reason or RESCHEDULE_REASON
        await self._cancel_existing_booking(
            booking=booking,
            class_session=class_session,
            now=now,
            actor_user_id=reschedule_in.actor_user_id,
            reason=reason,
            event_type=BookingEventType.RESCHEDULED_FROM,
            enforce_student_cutoff=enforce_student_cutoff,
        )
        new_booking = await self._create_one_on_one_booking(
            booking_in=OneOnOneBookingCreate(
                student_id=booking.student_id,
                teacher_availability_slot_id=reschedule_in.teacher_availability_slot_id,
            ),
            now=now,
            event_type=BookingEventType.RESCHEDULED_TO,
            reason=reason,
            actor_user_id=reschedule_in.actor_user_id,
            event_metadata={"rescheduled_from_booking_id": str(booking.id)},
            commit=True,
        )
        return new_booking

    async def _reschedule_batch_booking(
        self,
        *,
        booking_id: UUID,
        reschedule_in: BatchBookingReschedule,
        enforce_student_cutoff: bool,
    ) -> Booking:
        await self._get_optional_user(reschedule_in.actor_user_id)
        booking = await self._get_booking_for_update(booking_id)
        class_session = await self._get_class_session_for_update(booking.class_session_id)
        if class_session.program_type != StudentProgramType.BATCH:
            raise ConflictError("Booking is not for a batch class")

        now = utc_now()
        reason = reschedule_in.reason or RESCHEDULE_REASON
        await self._cancel_existing_booking(
            booking=booking,
            class_session=class_session,
            now=now,
            actor_user_id=reschedule_in.actor_user_id,
            reason=reason,
            event_type=BookingEventType.RESCHEDULED_FROM,
            enforce_student_cutoff=enforce_student_cutoff,
        )
        new_booking = await self._create_batch_booking(
            booking_in=BatchBookingCreate(
                student_id=booking.student_id,
                class_session_id=reschedule_in.class_session_id,
            ),
            now=now,
            event_type=BookingEventType.RESCHEDULED_TO,
            reason=reason,
            actor_user_id=reschedule_in.actor_user_id,
            event_metadata={"rescheduled_from_booking_id": str(booking.id)},
            commit=True,
        )
        return new_booking

    async def _cancel_existing_booking(
        self,
        *,
        booking: Booking,
        class_session: ClassSession,
        now: datetime,
        actor_user_id: UUID | None,
        reason: str,
        event_type: BookingEventType,
        enforce_student_cutoff: bool,
    ) -> None:
        if booking.status != BookingStatus.BOOKED:
            raise ConflictError("Booking is not active")

        if enforce_student_cutoff:
            self._ensure_student_can_change_booking(class_session=class_session, now=now)

        booking.status = BookingStatus.CANCELLED
        self._add_booking_event(
            booking_id=booking.id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            reason=reason,
            event_metadata={},
        )
        await self.session.flush()

        if class_session.program_type == StudentProgramType.ONE_ON_ONE:
            await self._cancel_one_on_one_class_session(class_session, now=now)
        if class_session.program_type == StudentProgramType.BATCH:
            await self._cancel_empty_batch_class_session(
                booking=booking,
                class_session=class_session,
                actor_user_id=actor_user_id,
            )

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

    async def _get_booking_for_update(self, booking_id: UUID) -> Booking:
        booking = await self.session.scalar(
            select(Booking).where(Booking.id == booking_id).with_for_update()
        )
        if booking is None:
            raise NotFoundError("Booking not found")
        return booking

    async def _get_student(self, student_id: UUID) -> Student:
        student = await self.session.get(Student, student_id)
        if student is None:
            raise NotFoundError("Student not found")
        return student

    async def _get_optional_user(self, user_id: UUID | None) -> User | None:
        if user_id is None:
            return None
        user = await self.session.get(User, user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    async def _get_teacher_availability_slot_for_update(
        self,
        slot_id: UUID,
    ) -> TeacherAvailabilitySlot:
        slot = await self.session.scalar(
            select(TeacherAvailabilitySlot)
            .where(TeacherAvailabilitySlot.id == slot_id)
            .with_for_update()
        )
        if slot is None:
            raise NotFoundError("Teacher availability slot not found")
        return slot

    async def _get_class_session_for_update(self, class_session_id: UUID) -> ClassSession:
        class_session = await self.session.scalar(
            select(ClassSession).where(ClassSession.id == class_session_id).with_for_update()
        )
        if class_session is None:
            raise NotFoundError("Class session not found")
        return class_session

    async def _get_active_student_batch_membership(
        self,
        student_id: UUID,
    ) -> StudentBatchMembership | None:
        return await self.session.scalar(
            select(StudentBatchMembership).where(
                StudentBatchMembership.student_id == student_id,
                StudentBatchMembership.is_active.is_(True),
            )
        )

    def _ensure_student_can_book(
        self,
        *,
        student: Student,
        expected_program_type: StudentProgramType,
        now: datetime,
    ) -> None:
        if student.program_type != expected_program_type:
            raise ConflictError("Student program type does not match this booking flow")
        self._ensure_student_has_active_access(student=student, now=now)

    def _ensure_student_has_active_access(
        self,
        *,
        student: Student,
        now: datetime,
    ) -> None:
        if student.status != StudentStatus.ACTIVE:
            raise ConflictError("Student is not active")
        if student.access_starts_at is None or student.access_ends_at is None:
            raise ConflictError("Student does not have an active access window")

        access_starts_at = _normalize_utc_datetime(student.access_starts_at)
        access_ends_at = _normalize_utc_datetime(student.access_ends_at)
        normalized_now = _normalize_utc_datetime(now)
        if normalized_now < access_starts_at or normalized_now >= access_ends_at:
            raise ConflictError("Student access window is not currently valid")

    def _ensure_student_access_covers_class(
        self,
        student: Student,
        class_starts_at: datetime,
    ) -> None:
        if student.access_starts_at is None or student.access_ends_at is None:
            raise ConflictError("Student does not have an active access window")
        starts_at = _normalize_utc_datetime(student.access_starts_at)
        ends_at = _normalize_utc_datetime(student.access_ends_at)
        class_time = _normalize_utc_datetime(class_starts_at)
        if class_time < starts_at or class_time >= ends_at:
            raise ConflictError("Student access does not cover this batch option")

    async def _ensure_no_booked_class_on_day(
        self,
        *,
        student_id: UUID,
        class_starts_at: datetime,
    ) -> None:
        await self._ensure_no_active_class_on_day(
            student_id=student_id,
            class_starts_at=class_starts_at,
        )

    async def _ensure_no_active_class_on_day(
        self,
        *,
        student_id: UUID,
        class_starts_at: datetime,
    ) -> None:
        day_start = datetime.combine(
            _normalize_utc_datetime(class_starts_at).date(),
            time.min,
            tzinfo=UTC,
        )
        day_end = day_start + timedelta(days=1)
        existing_booking = await self.session.scalar(
            select(Booking)
            .join(ClassSession, Booking.class_session_id == ClassSession.id)
            .where(
                Booking.student_id == student_id,
                Booking.status != BookingStatus.CANCELLED,
                ClassSession.status != ClassSessionStatus.CANCELLED,
                ClassSession.starts_at >= day_start,
                ClassSession.starts_at < day_end,
            )
        )
        if existing_booking is not None:
            raise ConflictError("Student already has an active class on this day")

    async def _ensure_no_active_booking_for_class_session(
        self,
        *,
        student_id: UUID,
        class_session_id: UUID,
    ) -> None:
        existing_booking = await self.session.scalar(
            select(Booking).where(
                Booking.student_id == student_id,
                Booking.class_session_id == class_session_id,
                Booking.status != BookingStatus.CANCELLED,
            )
        )
        if existing_booking is not None:
            raise ConflictError("Student already has an active booking for this class")

    async def _ensure_no_active_session_for_slot(self, slot_id: UUID) -> None:
        existing_session = await self.session.scalar(
            select(ClassSession).where(
                ClassSession.teacher_availability_slot_id == slot_id,
                ClassSession.status != ClassSessionStatus.CANCELLED,
            )
        )
        if existing_session is not None:
            raise ConflictError("Teacher availability slot already has an active class session")

    async def _ensure_class_session_capacity_available(self, class_session: ClassSession) -> None:
        active_booking_count = await self.session.scalar(
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.class_session_id == class_session.id,
                Booking.status != BookingStatus.CANCELLED,
            )
        )
        if active_booking_count >= class_session.capacity:
            raise ConflictError("Class session is full")

    def _ensure_student_can_change_booking(
        self,
        *,
        class_session: ClassSession,
        now: datetime,
    ) -> None:
        if class_session.starts_at <= now:
            raise BadRequestError("Cannot change a past or started booking")
        if class_session.starts_at - now < STUDENT_BOOKING_CHANGE_CUTOFF:
            raise ConflictError("Booking change window is closed")

    async def _cancel_one_on_one_class_session(
        self,
        class_session: ClassSession,
        *,
        now: datetime,
    ) -> None:
        if class_session.status == ClassSessionStatus.SCHEDULED:
            class_session.status = ClassSessionStatus.CANCELLED

        if class_session.starts_at <= now or class_session.teacher_availability_slot_id is None:
            return

        slot = await self.session.get(
            TeacherAvailabilitySlot,
            class_session.teacher_availability_slot_id,
        )
        if slot is not None and slot.status == AvailabilitySlotStatus.BOOKED:
            slot.status = AvailabilitySlotStatus.AVAILABLE

    async def _cancel_empty_batch_class_session(
        self,
        *,
        booking: Booking,
        class_session: ClassSession,
        actor_user_id: UUID | None,
    ) -> None:
        active_booking_count = await self.session.scalar(
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.class_session_id == class_session.id,
                Booking.status == BookingStatus.BOOKED,
            )
        )
        if (
            active_booking_count == 0
            and class_session.status == ClassSessionStatus.SCHEDULED
        ):
            class_session.status = ClassSessionStatus.CANCELLED
            self._add_booking_event(
                booking_id=booking.id,
                event_type=BookingEventType.CLASS_CANCELLED_EMPTY,
                actor_user_id=actor_user_id,
                reason=EMPTY_CLASS_REASON,
                event_metadata={"class_session_id": str(class_session.id)},
            )

    async def _mark_booking_attendance(
        self,
        *,
        booking: Booking,
        class_session: ClassSession,
        status: BookingStatus,
        actor_user_id: UUID | None,
        reason: str,
        now: datetime,
    ) -> None:
        self._ensure_can_mark_attendance(
            booking=booking,
            class_session=class_session,
            now=now,
        )

        old_status = booking.status
        booking.status = status
        self._add_booking_event(
            booking_id=booking.id,
            event_type=BookingEventType.ATTENDANCE_MARKED,
            actor_user_id=actor_user_id,
            reason=reason,
            event_metadata={
                "class_session_id": str(class_session.id),
                "old_status": old_status.value,
                "new_status": status.value,
            },
        )

    def _ensure_can_mark_attendance(
        self,
        *,
        booking: Booking,
        class_session: ClassSession,
        now: datetime,
    ) -> None:
        if booking.status == BookingStatus.CANCELLED:
            raise ConflictError("Cancelled bookings cannot be marked for attendance")
        if class_session.status == ClassSessionStatus.CANCELLED:
            raise ConflictError("Cancelled class sessions cannot be marked for attendance")
        if class_session.starts_at > now:
            raise BadRequestError("Attendance can only be marked after class start")

    async def _complete_class_session_if_attendance_marked(
        self,
        class_session: ClassSession,
    ) -> None:
        if class_session.status == ClassSessionStatus.CANCELLED:
            return

        active_booking_count = await self.session.scalar(
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.class_session_id == class_session.id,
                Booking.status != BookingStatus.CANCELLED,
            )
        )
        unmarked_booking_count = await self.session.scalar(
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.class_session_id == class_session.id,
                Booking.status == BookingStatus.BOOKED,
            )
        )
        if active_booking_count > 0 and unmarked_booking_count == 0:
            class_session.status = ClassSessionStatus.COMPLETED

    def _add_booking_event(
        self,
        *,
        booking_id: UUID,
        event_type: BookingEventType,
        actor_user_id: UUID | None,
        reason: str,
        event_metadata: dict,
    ) -> BookingEvent:
        event = BookingEvent(
            booking_id=booking_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            reason=reason,
            event_metadata=event_metadata,
        )
        self.session.add(event)
        return event


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _default_attendance_reason(status: BookingStatus) -> str:
    if status == BookingStatus.ATTENDED:
        return ATTENDED_REASON
    return MISSED_REASON
