from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.batch_groups.models import BatchGroup
from app.modules.batch_groups.schemas import (
    BatchSessionBulkGenerate,
    BatchSessionGenerationTemplate,
)
from app.modules.bookings.models import Booking, BookingEvent
from app.modules.classes.models import ClassSession
from app.modules.packages.models import Package
from app.modules.student_access_grants.models import StudentAccessGrant
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
from app.modules.users.models import User
from app.shared.enums import (
    BookingEventType,
    BookingStatus,
    ClassSessionStatus,
    DayOfWeek,
    StudentProgramType,
)
from app.shared.utils import utc_now

DAY_TO_INDEX = {
    DayOfWeek.MONDAY: 0,
    DayOfWeek.TUESDAY: 1,
    DayOfWeek.WEDNESDAY: 2,
    DayOfWeek.THURSDAY: 3,
    DayOfWeek.FRIDAY: 4,
    DayOfWeek.SATURDAY: 5,
    DayOfWeek.SUNDAY: 6,
}


class _BatchGroupShared:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _ensure_active_name_available(
        self,
        name: str,
        exclude_batch_group_id: UUID | None = None,
    ) -> None:
        statement = select(BatchGroup).where(
            BatchGroup.name == name,
            BatchGroup.is_active.is_(True),
        )
        if exclude_batch_group_id is not None:
            statement = statement.where(BatchGroup.id != exclude_batch_group_id)

        existing_batch_group = await self.session.scalar(statement)
        if existing_batch_group is not None:
            raise ConflictError("An active batch group with this name already exists")

    async def _get_batch_student(self, student_id: UUID) -> Student:
        student = await self.session.get(Student, student_id)
        if student is None:
            raise NotFoundError("Student not found")
        if student.program_type != StudentProgramType.BATCH:
            raise ConflictError("Only batch students can be assigned to a batch group")
        return student

    async def _get_optional_user(self, user_id: UUID | None) -> User | None:
        if user_id is None:
            return None

        user = await self.session.get(User, user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    async def _validate_generation_teachers(
        self,
        sessions: list[BatchSessionGenerationTemplate],
    ) -> None:
        teacher_ids = {session.teacher_id for session in sessions if session.teacher_id is not None}
        for teacher_id in teacher_ids:
            teacher = await self.session.get(Teacher, teacher_id)
            if teacher is None:
                raise NotFoundError("Teacher not found")

    def _build_expected_batch_sessions(
        self,
        batch_group: BatchGroup,
        generation_in: BatchSessionBulkGenerate,
    ) -> list[dict]:
        weekdays = {DAY_TO_INDEX[day] for day in generation_in.weekdays}
        expected_sessions: list[dict] = []

        current_date = generation_in.starts_from
        while current_date <= generation_in.starts_to:
            if current_date.weekday() in weekdays:
                for template in generation_in.sessions:
                    starts_at, ends_at = build_utc_session_datetimes(
                        session_date=current_date,
                        start_time_utc=template.start_time_utc,
                        end_time_utc=template.end_time_utc,
                    )
                    expected_sessions.append(
                        {
                            "teacher_id": template.teacher_id,
                            "teacher_availability_slot_id": None,
                            "batch_group_id": batch_group.id,
                            "program_type": StudentProgramType.BATCH,
                            "batch_slot": template.batch_slot,
                            "starts_at": starts_at,
                            "ends_at": ends_at,
                            "status": ClassSessionStatus.SCHEDULED,
                            "capacity": template.capacity or batch_group.default_capacity,
                        }
                    )
            current_date += timedelta(days=1)

        return expected_sessions

    def _ensure_no_overlaps_within_generation(self, expected_sessions: list[dict]) -> None:
        for index, expected_session in enumerate(expected_sessions):
            for other_session in expected_sessions[index + 1 :]:
                if _sessions_overlap(expected_session, other_session):
                    raise ConflictError("Bulk request contains overlapping batch sessions")

    async def _ensure_no_existing_batch_session_overlaps(
        self,
        *,
        batch_group_id: UUID,
        expected_sessions: list[dict],
    ) -> None:
        for expected_session in expected_sessions:
            existing_session = await self.session.scalar(
                select(ClassSession).where(
                    ClassSession.batch_group_id == batch_group_id,
                    ClassSession.status != ClassSessionStatus.CANCELLED,
                    ClassSession.starts_at < expected_session["ends_at"],
                    ClassSession.ends_at > expected_session["starts_at"],
                )
            )
            if existing_session is not None:
                raise ConflictError("Batch group already has an overlapping class session")

    async def _cancel_future_group_activity(self, batch_group_id: UUID) -> None:
        now = utc_now()
        result = await self.session.execute(
            select(Booking, ClassSession)
            .join(ClassSession, Booking.class_session_id == ClassSession.id)
            .where(
                ClassSession.batch_group_id == batch_group_id,
                ClassSession.starts_at > now,
                Booking.status == BookingStatus.BOOKED,
            )
        )
        for booking, _class_session in result.all():
            booking.status = BookingStatus.CANCELLED
            self.session.add(
                BookingEvent(
                    booking_id=booking.id,
                    event_type=BookingEventType.CANCELLED_BY_ADMIN,
                    actor_user_id=None,
                    reason="batch group voided",
                    event_metadata={},
                )
            )

        future_sessions = await self.session.scalars(
            select(ClassSession).where(
                ClassSession.batch_group_id == batch_group_id,
                ClassSession.starts_at > now,
                ClassSession.status == ClassSessionStatus.SCHEDULED,
            )
        )
        for class_session in future_sessions:
            class_session.status = ClassSessionStatus.CANCELLED

    async def _cancel_future_student_bookings_for_batch_group(
        self,
        *,
        student_id: UUID,
        batch_group_id: UUID,
        now: datetime,
    ) -> None:
        result = await self.session.execute(
            select(Booking, ClassSession)
            .join(ClassSession, Booking.class_session_id == ClassSession.id)
            .where(
                Booking.student_id == student_id,
                Booking.status == BookingStatus.BOOKED,
                ClassSession.batch_group_id == batch_group_id,
                ClassSession.starts_at > now,
            )
        )
        for booking, _class_session in result.all():
            booking.status = BookingStatus.CANCELLED
            self.session.add(
                BookingEvent(
                    booking_id=booking.id,
                    event_type=BookingEventType.CANCELLED_BY_ADMIN,
                    actor_user_id=None,
                    reason="batch transfer",
                    event_metadata={},
                )
            )

    async def _get_package(
        self,
        package_id: UUID,
        *,
        require_active: bool,
    ) -> Package:
        package = await self.session.get(Package, package_id)
        if package is None:
            raise NotFoundError("Package not found")
        if require_active and not package.is_active:
            raise ConflictError("Active batch groups require an active package")
        return package

    async def _validate_student_package_access(
        self,
        student_id: UUID,
        batch_group: BatchGroup,
        *,
        allow_override: bool,
    ) -> None:
        if allow_override:
            return
        if batch_group.package_id is None:
            raise ConflictError("Batch group has no package; package access override is required")
        now = utc_now()
        matching_grant_id = await self.session.scalar(
            select(StudentAccessGrant.id).where(
                StudentAccessGrant.student_id == student_id,
                StudentAccessGrant.package_id == batch_group.package_id,
                StudentAccessGrant.access_starts_at <= now,
                StudentAccessGrant.access_ends_at > now,
            )
        )
        if matching_grant_id is None:
            raise ConflictError(
                "Student does not have current access for the batch group's package"
            )


def build_utc_session_datetimes(
    *,
    session_date: date,
    start_time_utc: time,
    end_time_utc: time,
) -> tuple[datetime, datetime]:
    starts_at = datetime.combine(session_date, start_time_utc, tzinfo=UTC)
    ends_at = datetime.combine(session_date, end_time_utc, tzinfo=UTC)
    if end_time_utc < start_time_utc:
        ends_at += timedelta(days=1)
    return starts_at, ends_at


def _sessions_overlap(first_session: dict, second_session: dict) -> bool:
    return (
        first_session["starts_at"] < second_session["ends_at"]
        and first_session["ends_at"] > second_session["starts_at"]
    )
