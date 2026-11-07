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
    OneOnOneBookingCreate,
    OneOnOneBookingReschedule,
)
from app.modules.classes.models import ClassSession
from app.modules.notifications.service import NotificationService
from app.modules.schedules.models import TeacherAvailabilitySlot
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
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
MANUAL_ADD_REASON = "manually added by admin"
CLASS_CANCEL_REASON = "class cancelled by admin"
TEACHER_CLASS_CANCEL_REASON = "class cancelled by teacher"


class _BookingShared:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
        await self._emit_booking_created_notification(
            booking=booking,
            student=student,
            class_session=class_session,
            event_type=event_type,
            actor_user_id=actor_user_id,
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
        await self._emit_booking_created_notification(
            booking=booking,
            student=student,
            class_session=class_session,
            event_type=event_type,
            actor_user_id=actor_user_id,
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
        student = await self._get_student(booking.student_id)
        await self._emit_booking_cancelled_notification(
            booking=booking,
            student=student,
            class_session=class_session,
            event_type=event_type,
            actor_user_id=actor_user_id,
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
        if active_booking_count == 0 and class_session.status == ClassSessionStatus.SCHEDULED:
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
        await self._emit_attendance_notification(
            booking=booking,
            class_session=class_session,
            status=status,
            actor_user_id=actor_user_id,
        )

    async def _emit_booking_created_notification(
        self,
        *,
        booking: Booking,
        student: Student,
        class_session: ClassSession,
        event_type: BookingEventType,
        actor_user_id: UUID | None,
    ) -> None:
        service = NotificationService(self.session)
        is_reschedule = event_type == BookingEventType.RESCHEDULED_TO
        audiences = {"student": [student.user_id]}
        teacher_name = None
        if class_session.teacher_id is not None:
            teacher = await self.session.get(Teacher, class_session.teacher_id)
            if teacher is not None:
                audiences["teacher"] = [teacher.user_id]
                teacher_name = teacher.display_name
        student_user = await self.session.get(User, student.user_id)
        await service.emit_to_audiences(
            event_type="booking.rescheduled" if is_reschedule else "booking.created",
            aggregate_type="booking",
            aggregate_id=booking.id,
            dedupe_key=(
                f"notification:booking:{'rescheduled' if is_reschedule else 'created'}:{booking.id}"
            ),
            audiences=audiences,
            category="classes",
            priority="high" if is_reschedule else "medium",
            data={
                "class_id": str(class_session.id),
                "booking_id": str(booking.id),
                "starts_at": class_session.starts_at.isoformat(),
                "ends_at": class_session.ends_at.isoformat(),
                "teacher_name": teacher_name,
                "student_name": student_user.full_name if student_user else None,
                "program_type": class_session.program_type.value,
            },
            actor_user_id=actor_user_id,
            include_admins=True,
        )

    async def _emit_booking_cancelled_notification(
        self,
        *,
        booking: Booking,
        student: Student,
        class_session: ClassSession,
        event_type: BookingEventType,
        actor_user_id: UUID | None,
    ) -> None:
        service = NotificationService(self.session)
        audiences = {"student": [student.user_id]}
        teacher_name = None
        if class_session.teacher_id is not None:
            teacher = await self.session.get(Teacher, class_session.teacher_id)
            if teacher is not None:
                audiences["teacher"] = [teacher.user_id]
                teacher_name = teacher.display_name
        student_user = await self.session.get(User, student.user_id)
        await service.emit_to_audiences(
            event_type="booking.cancelled",
            aggregate_type="booking",
            aggregate_id=booking.id,
            dedupe_key=f"notification:booking:cancelled:{booking.id}",
            audiences=audiences,
            category="classes",
            priority="high",
            data={
                "class_id": str(class_session.id),
                "booking_id": str(booking.id),
                "starts_at": class_session.starts_at.isoformat(),
                "ends_at": class_session.ends_at.isoformat(),
                "teacher_name": teacher_name,
                "student_name": student_user.full_name if student_user else None,
                "program_type": class_session.program_type.value,
            },
            actor_user_id=actor_user_id,
            include_admins=True,
        )

    async def _emit_attendance_notification(
        self,
        *,
        booking: Booking,
        class_session: ClassSession,
        status: BookingStatus,
        actor_user_id: UUID | None,
    ) -> None:
        student = await self._get_student(booking.student_id)
        teacher_name = None
        if class_session.teacher_id is not None:
            teacher = await self.session.get(Teacher, class_session.teacher_id)
            if teacher is not None:
                teacher_name = teacher.display_name
        service = NotificationService(self.session)
        missed = status == BookingStatus.MISSED
        audiences = {"student": [student.user_id]}
        await service.emit_to_audiences(
            event_type="booking.attendance_marked",
            aggregate_type="booking",
            aggregate_id=booking.id,
            dedupe_key=f"notification:attendance:{booking.id}:{status.value}",
            audiences=audiences,
            category="classes",
            priority="medium",
            data={
                "class_id": str(class_session.id),
                "booking_id": str(booking.id),
                "starts_at": class_session.starts_at.isoformat(),
                "ends_at": class_session.ends_at.isoformat(),
                "teacher_name": teacher_name,
                "student_name": (await self.session.get(User, student.user_id)).full_name,
                "attendance_status": status.value,
            },
            actor_user_id=actor_user_id,
            include_admins=missed,
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
