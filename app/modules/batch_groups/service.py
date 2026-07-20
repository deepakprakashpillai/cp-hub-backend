from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.batch_groups.models import BatchGroup, StudentBatchMembership
from app.modules.batch_groups.schemas import (
    BatchGroupCreate,
    BatchGroupUpdate,
    BatchSessionBulkGenerate,
    BatchSessionGenerationTemplate,
    StudentBatchMembershipAssign,
    StudentBatchTransfer,
)
from app.modules.bookings.models import Booking
from app.modules.classes.models import ClassSession
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
from app.modules.users.models import User
from app.shared.enums import BookingStatus, ClassSessionStatus, DayOfWeek, StudentProgramType
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


class BatchGroupService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_batch_groups(self, is_active: bool | None = None) -> list[BatchGroup]:
        statement = select(BatchGroup).order_by(BatchGroup.created_at.desc())
        if is_active is not None:
            statement = statement.where(BatchGroup.is_active.is_(is_active))

        result = await self.session.scalars(statement)
        return list(result)

    async def get_batch_group(self, batch_group_id: UUID) -> BatchGroup:
        batch_group = await self.session.get(BatchGroup, batch_group_id)
        if batch_group is None:
            raise NotFoundError("Batch group not found")
        return batch_group

    async def create_batch_group(self, batch_group_in: BatchGroupCreate) -> BatchGroup:
        if batch_group_in.is_active:
            await self._ensure_active_name_available(batch_group_in.name)

        batch_group = BatchGroup(**batch_group_in.model_dump())
        self.session.add(batch_group)
        await self.session.commit()
        await self.session.refresh(batch_group)
        return batch_group

    async def update_batch_group(
        self,
        batch_group_id: UUID,
        batch_group_in: BatchGroupUpdate,
    ) -> BatchGroup:
        batch_group = await self.get_batch_group(batch_group_id)
        update_data = batch_group_in.model_dump(exclude_unset=True)

        for non_nullable_field in ("name", "default_capacity", "is_active"):
            if non_nullable_field in update_data and update_data[non_nullable_field] is None:
                raise BadRequestError(f"{non_nullable_field} cannot be null")

        final_name = update_data.get("name", batch_group.name)
        final_is_active = update_data.get("is_active", batch_group.is_active)
        if final_is_active:
            await self._ensure_active_name_available(
                final_name,
                exclude_batch_group_id=batch_group.id,
            )

        for field, value in update_data.items():
            setattr(batch_group, field, value)

        if batch_group.is_active is False:
            await self._cancel_future_group_activity(batch_group.id)

        await self.session.commit()
        await self.session.refresh(batch_group)
        return batch_group

    async def void_batch_group(self, batch_group_id: UUID) -> BatchGroup:
        batch_group = await self.get_batch_group(batch_group_id)
        batch_group.is_active = False
        await self._cancel_future_group_activity(batch_group.id)
        await self.session.commit()
        await self.session.refresh(batch_group)
        return batch_group

    async def list_batch_group_students(
        self,
        batch_group_id: UUID,
        is_active: bool | None = True,
    ) -> list[StudentBatchMembership]:
        await self.get_batch_group(batch_group_id)
        statement = (
            select(StudentBatchMembership)
            .where(StudentBatchMembership.batch_group_id == batch_group_id)
            .order_by(StudentBatchMembership.created_at.desc())
        )
        if is_active is not None:
            statement = statement.where(StudentBatchMembership.is_active.is_(is_active))

        result = await self.session.scalars(statement)
        return list(result)

    async def assign_student_to_batch_group(
        self,
        batch_group_id: UUID,
        membership_in: StudentBatchMembershipAssign,
    ) -> StudentBatchMembership:
        batch_group = await self.get_batch_group(batch_group_id)
        if not batch_group.is_active:
            raise ConflictError("Cannot assign students to an inactive batch group")

        student = await self._get_batch_student(membership_in.student_id)
        await self._get_optional_user(membership_in.assigned_by_user_id)

        active_membership = await self.get_active_student_membership(student.id)
        if active_membership is not None:
            if active_membership.batch_group_id == batch_group.id:
                raise ConflictError("Student is already active in this batch group")
            raise ConflictError("Student already has an active batch membership")

        membership = StudentBatchMembership(
            student_id=student.id,
            batch_group_id=batch_group.id,
            is_active=True,
            assigned_by_user_id=membership_in.assigned_by_user_id,
            assigned_at=utc_now(),
            end_reason=None,
        )
        self.session.add(membership)
        await self.session.commit()
        await self.session.refresh(membership)
        return membership

    async def transfer_student_batch_group(
        self,
        student_id: UUID,
        transfer_in: StudentBatchTransfer,
    ) -> StudentBatchMembership:
        student = await self._get_batch_student(student_id)
        batch_group = await self.get_batch_group(transfer_in.batch_group_id)
        if not batch_group.is_active:
            raise ConflictError("Cannot transfer student to an inactive batch group")
        await self._get_optional_user(transfer_in.assigned_by_user_id)

        active_membership = await self.get_active_student_membership(student.id)
        if active_membership is not None and active_membership.batch_group_id == batch_group.id:
            raise ConflictError("Student is already active in this batch group")

        now = utc_now()
        if active_membership is not None:
            active_membership.is_active = False
            active_membership.ended_at = now
            active_membership.end_reason = transfer_in.reason
            await self._cancel_future_student_bookings_for_batch_group(
                student_id=student.id,
                batch_group_id=active_membership.batch_group_id,
                now=now,
            )

        membership = StudentBatchMembership(
            student_id=student.id,
            batch_group_id=batch_group.id,
            is_active=True,
            assigned_by_user_id=transfer_in.assigned_by_user_id,
            assigned_at=now,
            end_reason=None,
        )
        self.session.add(membership)
        await self.session.commit()
        await self.session.refresh(membership)
        return membership

    async def list_student_batch_memberships(
        self,
        student_id: UUID,
    ) -> list[StudentBatchMembership]:
        student = await self.session.get(Student, student_id)
        if student is None:
            raise NotFoundError("Student not found")

        result = await self.session.scalars(
            select(StudentBatchMembership)
            .where(StudentBatchMembership.student_id == student_id)
            .order_by(StudentBatchMembership.assigned_at.desc())
        )
        return list(result)

    async def get_active_student_membership(
        self,
        student_id: UUID,
    ) -> StudentBatchMembership | None:
        return await self.session.scalar(
            select(StudentBatchMembership).where(
                StudentBatchMembership.student_id == student_id,
                StudentBatchMembership.is_active.is_(True),
            )
        )

    async def end_active_student_membership(
        self,
        student_id: UUID,
        *,
        reason: str | None,
        now: datetime | None = None,
        commit: bool = True,
    ) -> bool:
        active_membership = await self.get_active_student_membership(student_id)
        if active_membership is None:
            return False

        ended_at = now or utc_now()
        active_membership.is_active = False
        active_membership.ended_at = ended_at
        active_membership.end_reason = reason

        if commit:
            await self.session.commit()

        return True

    async def generate_batch_sessions(
        self,
        batch_group_id: UUID,
        generation_in: BatchSessionBulkGenerate,
    ) -> list[ClassSession]:
        batch_group = await self.get_batch_group(batch_group_id)
        if not batch_group.is_active:
            raise ConflictError("Cannot generate sessions for an inactive batch group")

        await self._validate_generation_teachers(generation_in.sessions)
        expected_sessions = self._build_expected_batch_sessions(batch_group, generation_in)
        self._ensure_no_overlaps_within_generation(expected_sessions)
        await self._ensure_no_existing_batch_session_overlaps(
            batch_group_id=batch_group.id,
            expected_sessions=expected_sessions,
        )

        class_sessions: list[ClassSession] = []
        for session_data in expected_sessions:
            class_session = ClassSession(**session_data)
            self.session.add(class_session)
            class_sessions.append(class_session)

        await self.session.commit()
        for class_session in class_sessions:
            await self.session.refresh(class_session)
        return class_sessions

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
