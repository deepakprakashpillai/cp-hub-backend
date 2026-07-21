from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.batch_groups.models import StudentBatchMembership
from app.modules.bookings.models import Booking, BookingEvent
from app.modules.bookings.schemas import (
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
from app.modules.users.models import User
from app.shared.enums import (
    AvailabilitySlotStatus,
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


class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_bookings(
        self,
        student_id: UUID | None = None,
        class_session_id: UUID | None = None,
    ) -> list[Booking]:
        statement = select(Booking).order_by(Booking.created_at.desc())
        if student_id is not None:
            statement = statement.where(Booking.student_id == student_id)
        if class_session_id is not None:
            statement = statement.where(Booking.class_session_id == class_session_id)

        result = await self.session.scalars(statement)
        return list(result)

    async def get_booking(self, booking_id: UUID) -> Booking:
        booking = await self.session.get(Booking, booking_id)
        if booking is None:
            raise NotFoundError("Booking not found")
        return booking

    async def list_booking_events(self, booking_id: UUID) -> list[BookingEvent]:
        await self.get_booking(booking_id)
        result = await self.session.scalars(
            select(BookingEvent)
            .where(BookingEvent.booking_id == booking_id)
            .order_by(BookingEvent.created_at.asc())
        )
        return list(result)

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
        await self._ensure_batch_capacity_available(class_session)

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
        if student.status != StudentStatus.ACTIVE:
            raise ConflictError("Student is not active")
        if student.access_starts_at is None or student.access_ends_at is None:
            raise ConflictError("Student does not have an active access window")

        access_starts_at = _normalize_utc_datetime(student.access_starts_at)
        access_ends_at = _normalize_utc_datetime(student.access_ends_at)
        normalized_now = _normalize_utc_datetime(now)
        if normalized_now < access_starts_at or normalized_now >= access_ends_at:
            raise ConflictError("Student access window is not currently valid")

    async def _ensure_no_booked_class_on_day(
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
                Booking.status == BookingStatus.BOOKED,
                ClassSession.status == ClassSessionStatus.SCHEDULED,
                ClassSession.starts_at >= day_start,
                ClassSession.starts_at < day_end,
            )
        )
        if existing_booking is not None:
            raise ConflictError("Student already has a booked class on this day")

    async def _ensure_no_active_session_for_slot(self, slot_id: UUID) -> None:
        existing_session = await self.session.scalar(
            select(ClassSession).where(
                ClassSession.teacher_availability_slot_id == slot_id,
                ClassSession.status != ClassSessionStatus.CANCELLED,
            )
        )
        if existing_session is not None:
            raise ConflictError("Teacher availability slot already has an active class session")

    async def _ensure_batch_capacity_available(self, class_session: ClassSession) -> None:
        active_booking_count = await self.session.scalar(
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.class_session_id == class_session.id,
                Booking.status == BookingStatus.BOOKED,
            )
        )
        if active_booking_count >= class_session.capacity:
            raise ConflictError("Batch class session is full")

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
