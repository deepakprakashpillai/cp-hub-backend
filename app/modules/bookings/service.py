from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import BatchBookingCreate, OneOnOneBookingCreate
from app.modules.classes.models import ClassSession
from app.modules.schedules.models import TeacherAvailabilitySlot
from app.modules.students.models import Student
from app.shared.enums import (
    AvailabilitySlotStatus,
    BookingStatus,
    ClassSessionStatus,
    StudentProgramType,
    StudentStatus,
)
from app.shared.utils import utc_now

BATCH_BOOKING_CLOSES_BEFORE_START = timedelta(hours=3)


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

    async def create_one_on_one_booking(self, booking_in: OneOnOneBookingCreate) -> Booking:
        now = utc_now()
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

        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    async def create_batch_booking(self, booking_in: BatchBookingCreate) -> Booking:
        now = utc_now()
        student = await self._get_student(booking_in.student_id)
        self._ensure_student_can_book(
            student=student,
            expected_program_type=StudentProgramType.BATCH,
            now=now,
        )

        class_session = await self._get_class_session_for_update(booking_in.class_session_id)
        if class_session.program_type != StudentProgramType.BATCH:
            raise ConflictError("Class session is not a batch session")
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
        await self.session.commit()
        await self.session.refresh(booking)
        return booking

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

    async def _get_student(self, student_id: UUID) -> Student:
        student = await self.session.get(Student, student_id)
        if student is None:
            raise NotFoundError("Student not found")
        return student

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


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
