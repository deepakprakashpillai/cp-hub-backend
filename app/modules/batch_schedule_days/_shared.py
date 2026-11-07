from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.batch_groups.models import BatchGroup, StudentBatchMembership
from app.modules.batch_schedule_days.models import (
    BatchScheduleDay,
    BatchScheduleDayEvent,
)
from app.modules.batch_schedule_days.schemas import (
    BatchDayActionRequest,
    BatchDayBatchSummary,
    BatchDayCreate,
    BatchDayOptionCreate,
    BatchDayOptionRead,
    BatchDayStudentSummary,
    BatchDayTeacherSummary,
    BatchScheduleDayRead,
    BatchScheduleDefaultsRead,
)
from app.modules.bookings.models import Booking, BookingEvent
from app.modules.classes.models import ClassSession
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
from app.modules.users.models import User
from app.shared.enums import (
    BatchCapacityStrategy,
    BatchScheduleDayStatus,
    BookingEventType,
    BookingStatus,
    ClassSessionStatus,
    DayOfWeek,
    StudentProgramType,
    StudentStatus,
)

DEFAULTS_ID = UUID("00000000-0000-0000-0000-000000000001")
DAY_TO_INDEX = {
    DayOfWeek.MONDAY: 0,
    DayOfWeek.TUESDAY: 1,
    DayOfWeek.WEDNESDAY: 2,
    DayOfWeek.THURSDAY: 3,
    DayOfWeek.FRIDAY: 4,
    DayOfWeek.SATURDAY: 5,
    DayOfWeek.SUNDAY: 6,
}
DEFAULT_TEMPLATES = [
    {"display_label": "Morning", "start_time_utc": "08:00:00", "duration_minutes": 60},
    {"display_label": "Noon", "start_time_utc": "12:00:00", "duration_minutes": 60},
    {"display_label": "Evening", "start_time_utc": "18:00:00", "duration_minutes": 60},
]


class _BatchScheduleDayShared:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _create_day(self, day_in: BatchDayCreate) -> BatchScheduleDay:
        if day_in.options is None:
            defaults = BatchScheduleDefaultsRead.model_validate(await self.get_defaults())
            default_teacher_id = (
                day_in.default_teacher_id
                if "default_teacher_id" in day_in.model_fields_set
                else defaults.default_teacher_id
            )
            templates = defaults.option_templates[: defaults.default_option_count]
            options = []
            for template in templates:
                starts_at = datetime.combine(
                    day_in.schedule_date,
                    template.start_time_utc,
                    tzinfo=UTC,
                )
                capacity = template.capacity
                if capacity is None and defaults.capacity_strategy == BatchCapacityStrategy.FIXED:
                    capacity = defaults.fixed_capacity
                options.append(
                    BatchDayOptionCreate(
                        display_label=template.display_label,
                        starts_at=starts_at,
                        ends_at=starts_at + timedelta(minutes=template.duration_minutes),
                        teacher_id=template.teacher_id,
                        capacity=capacity,
                    )
                )
            day_in = BatchDayCreate(
                batch_group_id=day_in.batch_group_id,
                schedule_date=day_in.schedule_date,
                default_teacher_id=default_teacher_id,
                actor_user_id=day_in.actor_user_id,
                options=options,
            )
        batch_group = await self.session.get(BatchGroup, day_in.batch_group_id)
        if batch_group is None:
            raise NotFoundError("Batch group not found")
        if not batch_group.is_active:
            raise ConflictError("Cannot schedule an inactive batch group")
        await self._get_optional_user(day_in.actor_user_id)
        if day_in.default_teacher_id is not None:
            await self._get_active_teacher(day_in.default_teacher_id)
        existing = await self.session.scalar(
            select(BatchScheduleDay.id).where(
                BatchScheduleDay.batch_group_id == day_in.batch_group_id,
                BatchScheduleDay.schedule_date == day_in.schedule_date,
            )
        )
        if existing is not None:
            raise ConflictError("Batch schedule day already exists for this group and date")
        self._ensure_no_request_overlaps(day_in.options)

        teacher_ids = {
            option.teacher_id or day_in.default_teacher_id
            for option in day_in.options
            if option.teacher_id is not None or day_in.default_teacher_id is not None
        }
        for teacher_id in teacher_ids:
            await self._get_active_teacher(teacher_id)
        for option in day_in.options:
            await self._ensure_no_group_overlap(
                day_in.batch_group_id,
                option.starts_at,
                option.ends_at,
            )
            teacher_id = option.teacher_id or day_in.default_teacher_id
            if teacher_id is not None:
                await self._ensure_no_teacher_overlap(
                    teacher_id,
                    option.starts_at,
                    option.ends_at,
                )

        day = BatchScheduleDay(
            batch_group_id=day_in.batch_group_id,
            schedule_date=day_in.schedule_date,
            created_by_user_id=day_in.actor_user_id,
        )
        self.session.add(day)
        await self.session.flush()
        for index, option in enumerate(day_in.options, start=1):
            self.session.add(
                ClassSession(
                    teacher_id=option.teacher_id or day_in.default_teacher_id,
                    teacher_availability_slot_id=None,
                    batch_group_id=batch_group.id,
                    batch_schedule_day_id=day.id,
                    program_type=StudentProgramType.BATCH,
                    batch_slot=None,
                    display_label=option.display_label,
                    option_order=index,
                    starts_at=option.starts_at,
                    ends_at=option.ends_at,
                    status=ClassSessionStatus.SCHEDULED,
                    capacity=option.capacity or batch_group.default_capacity,
                )
            )
        await self.session.flush()
        return day

    async def _read_days(
        self,
        day_ids: list[UUID],
        *,
        day_rows=None,
    ) -> list[BatchScheduleDayRead]:
        if not day_ids:
            return []
        if day_rows is None:
            day_rows = list(
                (
                    await self.session.execute(
                        select(BatchScheduleDay, BatchGroup)
                        .join(BatchGroup, BatchGroup.id == BatchScheduleDay.batch_group_id)
                        .where(BatchScheduleDay.id.in_(day_ids))
                    )
                ).all()
            )
        day_by_id = {day.id: (day, batch) for day, batch in day_rows}
        teacher_user = aliased(User)
        counts = (
            select(
                Booking.class_session_id.label("class_session_id"),
                func.count().label("active_booking_count"),
            )
            .where(Booking.status == BookingStatus.BOOKED)
            .group_by(Booking.class_session_id)
            .subquery()
        )
        option_rows = (
            await self.session.execute(
                select(
                    ClassSession,
                    Teacher,
                    teacher_user,
                    func.coalesce(counts.c.active_booking_count, 0),
                )
                .outerjoin(Teacher, Teacher.id == ClassSession.teacher_id)
                .outerjoin(teacher_user, teacher_user.id == Teacher.user_id)
                .outerjoin(counts, counts.c.class_session_id == ClassSession.id)
                .where(ClassSession.batch_schedule_day_id.in_(day_ids))
                .order_by(ClassSession.option_order.asc(), ClassSession.id.asc())
            )
        ).all()
        options_by_day = defaultdict(list)
        for class_session, teacher, user, active_count in option_rows:
            options_by_day[class_session.batch_schedule_day_id].append(
                BatchDayOptionRead(
                    id=class_session.id,
                    batch_schedule_day_id=class_session.batch_schedule_day_id,
                    display_label=class_session.display_label
                    or class_session.batch_slot.value.title(),
                    option_order=class_session.option_order or 1,
                    starts_at=class_session.starts_at,
                    ends_at=class_session.ends_at,
                    teacher_id=class_session.teacher_id,
                    teacher=(
                        BatchDayTeacherSummary(
                            id=teacher.id,
                            display_name=teacher.display_name,
                            full_name=user.full_name,
                        )
                        if teacher is not None
                        else None
                    ),
                    capacity=class_session.capacity,
                    active_booking_count=active_count,
                    available_capacity=max(class_session.capacity - active_count, 0),
                    status=class_session.status,
                )
            )

        group_ids = {day.batch_group_id for day, _batch in day_rows}
        student_user = aliased(User)
        membership_rows = (
            await self.session.execute(
                select(StudentBatchMembership, Student, student_user)
                .join(Student, Student.id == StudentBatchMembership.student_id)
                .join(student_user, student_user.id == Student.user_id)
                .where(
                    StudentBatchMembership.batch_group_id.in_(group_ids),
                    StudentBatchMembership.is_active.is_(True),
                    Student.status == StudentStatus.ACTIVE,
                )
            )
        ).all()
        students_by_group = defaultdict(list)
        for membership, student, user in membership_rows:
            students_by_group[membership.batch_group_id].append((student, user))

        selected_rows = (
            await self.session.execute(
                select(ClassSession.batch_schedule_day_id, Booking.student_id)
                .join(Booking, Booking.class_session_id == ClassSession.id)
                .where(
                    ClassSession.batch_schedule_day_id.in_(day_ids),
                    Booking.status != BookingStatus.CANCELLED,
                )
            )
        ).all()
        selected_by_day = defaultdict(set)
        for day_id, student_id in selected_rows:
            selected_by_day[day_id].add(student_id)

        reads = []
        for day_id in day_ids:
            day_row = day_by_id.get(day_id)
            if day_row is None:
                continue
            day, batch = day_row
            day_start = datetime.combine(day.schedule_date, time.min, tzinfo=UTC)
            day_end = day_start + timedelta(days=1)
            eligible = [
                (student, user)
                for student, user in students_by_group[day.batch_group_id]
                if student.access_starts_at is not None
                and student.access_ends_at is not None
                and student.access_starts_at < day_end
                and student.access_ends_at > day_start
            ]
            reads.append(
                BatchScheduleDayRead(
                    id=day.id,
                    batch_group_id=day.batch_group_id,
                    batch=BatchDayBatchSummary(id=batch.id, name=batch.name),
                    schedule_date=day.schedule_date,
                    status=day.status,
                    cancelled_at=day.cancelled_at,
                    cancelled_by_user_id=day.cancelled_by_user_id,
                    cancel_reason=day.cancel_reason,
                    options=options_by_day[day.id],
                    eligible_student_count=len(eligible),
                    unassigned_students=[
                        BatchDayStudentSummary(
                            id=student.id,
                            full_name=user.full_name,
                            email=user.email,
                        )
                        for student, user in eligible
                        if student.id not in selected_by_day[day.id]
                    ],
                    created_at=day.created_at,
                    updated_at=day.updated_at,
                )
            )
        return reads

    async def _validate_option(
        self,
        *,
        day: BatchScheduleDay,
        option: BatchDayOptionCreate,
        existing_sessions: list[ClassSession],
        exclude_session_id: UUID | None = None,
    ) -> None:
        if option.teacher_id is not None:
            await self._get_active_teacher(option.teacher_id)
        for existing in existing_sessions:
            if existing.id == exclude_session_id or existing.status == ClassSessionStatus.CANCELLED:
                continue
            existing_label = existing.display_label or existing.batch_slot.value
            if existing_label.casefold() == option.display_label.casefold():
                raise ConflictError("Option display label already exists for this batch day")
            if existing.starts_at < option.ends_at and existing.ends_at > option.starts_at:
                raise ConflictError("Batch-day options cannot overlap")
        await self._ensure_no_group_overlap(
            day.batch_group_id,
            option.starts_at,
            option.ends_at,
            exclude_session_id=exclude_session_id,
        )
        if option.teacher_id is not None:
            await self._ensure_no_teacher_overlap(
                option.teacher_id,
                option.starts_at,
                option.ends_at,
                exclude_session_id=exclude_session_id,
            )

    def _ensure_no_request_overlaps(self, options: list[BatchDayOptionCreate]) -> None:
        for index, option in enumerate(options):
            for other in options[index + 1 :]:
                if option.starts_at < other.ends_at and option.ends_at > other.starts_at:
                    raise ConflictError(
                        f"Options {option.display_label} and {other.display_label} overlap"
                    )

    async def _ensure_no_group_overlap(
        self,
        batch_group_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        *,
        exclude_session_id: UUID | None = None,
    ) -> None:
        statement = select(ClassSession.id).where(
            ClassSession.batch_group_id == batch_group_id,
            ClassSession.status != ClassSessionStatus.CANCELLED,
            ClassSession.starts_at < ends_at,
            ClassSession.ends_at > starts_at,
        )
        if exclude_session_id is not None:
            statement = statement.where(ClassSession.id != exclude_session_id)
        if await self.session.scalar(statement) is not None:
            raise ConflictError("Batch group already has an overlapping class session")

    async def _ensure_no_teacher_overlap(
        self,
        teacher_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        *,
        exclude_session_id: UUID | None = None,
    ) -> None:
        statement = select(ClassSession.id).where(
            ClassSession.teacher_id == teacher_id,
            ClassSession.status != ClassSessionStatus.CANCELLED,
            ClassSession.starts_at < ends_at,
            ClassSession.ends_at > starts_at,
        )
        if exclude_session_id is not None:
            statement = statement.where(ClassSession.id != exclude_session_id)
        if await self.session.scalar(statement) is not None:
            raise ConflictError("Teacher already has an overlapping class session")

    async def _get_day_model(self, day_id: UUID) -> BatchScheduleDay:
        day = await self.session.get(BatchScheduleDay, day_id)
        if day is None:
            raise NotFoundError("Batch schedule day not found")
        return day

    async def _lock_days(self, day_ids: list[UUID]) -> list[BatchScheduleDay]:
        days = list(
            await self.session.scalars(
                select(BatchScheduleDay)
                .where(BatchScheduleDay.id.in_(day_ids))
                .order_by(BatchScheduleDay.id.asc())
                .with_for_update()
            )
        )
        found = {day.id for day in days}
        missing = [day_id for day_id in day_ids if day_id not in found]
        if missing:
            raise NotFoundError(f"Batch schedule day not found: {missing[0]}")
        by_id = {day.id: day for day in days}
        return [by_id[day_id] for day_id in day_ids]

    async def _validate_days_can_be_cancelled(
        self,
        days: list[BatchScheduleDay],
    ) -> None:
        now = datetime.now(UTC)
        active_days = [day for day in days if day.status != BatchScheduleDayStatus.CANCELLED]
        if not active_days:
            return
        session_rows = list(
            await self.session.scalars(
                select(ClassSession)
                .where(ClassSession.batch_schedule_day_id.in_([day.id for day in active_days]))
                .order_by(ClassSession.id.asc())
                .with_for_update()
            )
        )
        sessions_by_day = defaultdict(list)
        for class_session in session_rows:
            sessions_by_day[class_session.batch_schedule_day_id].append(class_session)
        for day in active_days:
            sessions = sessions_by_day[day.id]
            if sessions and all(value.status == ClassSessionStatus.COMPLETED for value in sessions):
                raise ConflictError(
                    "Completed batch schedule day cannot be cancelled: "
                    f"{day.schedule_date.isoformat()}"
                )
            if not sessions or max(value.ends_at for value in sessions) <= now:
                raise ConflictError(
                    f"Past batch schedule day cannot be cancelled: {day.schedule_date.isoformat()}"
                )

    async def _cancel_locked_day(
        self,
        day: BatchScheduleDay,
        action_in: BatchDayActionRequest,
    ) -> None:
        reason = action_in.reason or "batch schedule day cancelled"
        sessions = list(
            await self.session.scalars(
                select(ClassSession)
                .where(
                    ClassSession.batch_schedule_day_id == day.id,
                    ClassSession.status == ClassSessionStatus.SCHEDULED,
                )
                .order_by(ClassSession.id.asc())
                .with_for_update()
            )
        )
        session_ids = [class_session.id for class_session in sessions]
        bookings = (
            list(
                await self.session.scalars(
                    select(Booking)
                    .where(
                        Booking.class_session_id.in_(session_ids),
                        Booking.status == BookingStatus.BOOKED,
                    )
                    .order_by(Booking.id.asc())
                    .with_for_update()
                )
            )
            if session_ids
            else []
        )
        for class_session in sessions:
            class_session.status = ClassSessionStatus.CANCELLED
        for booking in bookings:
            booking.status = BookingStatus.CANCELLED
            self.session.add(
                BookingEvent(
                    booking_id=booking.id,
                    event_type=BookingEventType.BATCH_DAY_CANCELLED,
                    actor_user_id=action_in.actor_user_id,
                    reason=reason,
                    event_metadata={
                        "source": "admin",
                        "batch_schedule_day_id": str(day.id),
                        "schedule_date": day.schedule_date.isoformat(),
                    },
                )
            )
        day.status = BatchScheduleDayStatus.CANCELLED
        day.cancelled_at = datetime.now(UTC)
        day.cancelled_by_user_id = action_in.actor_user_id
        day.cancel_reason = reason
        self.session.add(
            BatchScheduleDayEvent(
                batch_schedule_day_id=day.id,
                event_type="cancelled",
                actor_user_id=action_in.actor_user_id,
                reason=reason,
                event_metadata={
                    "cancelled_session_ids": [str(value) for value in session_ids],
                    "cancelled_booking_ids": [str(value.id) for value in bookings],
                },
            )
        )

    async def _get_day_sessions(self, day_id: UUID) -> list[ClassSession]:
        return list(
            await self.session.scalars(
                select(ClassSession).where(ClassSession.batch_schedule_day_id == day_id)
            )
        )

    async def _get_day_session_for_update(
        self,
        day_id: UUID,
        class_session_id: UUID,
    ) -> ClassSession:
        class_session = await self.session.scalar(
            select(ClassSession)
            .where(
                ClassSession.id == class_session_id,
                ClassSession.batch_schedule_day_id == day_id,
            )
            .with_for_update()
        )
        if class_session is None:
            raise NotFoundError("Batch-day option not found")
        return class_session

    async def _active_booking_count(self, class_session_id: UUID) -> int:
        return (
            await self.session.scalar(
                select(func.count())
                .select_from(Booking)
                .where(
                    Booking.class_session_id == class_session_id,
                    Booking.status == BookingStatus.BOOKED,
                )
            )
            or 0
        )

    async def _get_active_teacher(self, teacher_id: UUID) -> Teacher:
        teacher = await self.session.get(Teacher, teacher_id)
        if teacher is None:
            raise NotFoundError("Teacher not found")
        if not teacher.is_active:
            raise ConflictError("Teacher must be active")
        return teacher

    async def _get_optional_user(self, user_id: UUID | None) -> User | None:
        if user_id is None:
            return None
        user = await self.session.get(User, user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user
