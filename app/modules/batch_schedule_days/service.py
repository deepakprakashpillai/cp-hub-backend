from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_rows
from app.modules.batch_groups.models import BatchGroup, StudentBatchMembership
from app.modules.batch_schedule_days.models import (
    BatchScheduleDay,
    BatchScheduleDayEvent,
    BatchScheduleDefaults,
)
from app.modules.batch_schedule_days.schemas import (
    MAX_BATCH_DAY_OPTIONS,
    BatchDayActionRequest,
    BatchDayBatchSummary,
    BatchDayBulkCancelRequest,
    BatchDayBulkCancelResult,
    BatchDayBulkCreate,
    BatchDayBulkCreateResult,
    BatchDayCreate,
    BatchDayOptionCreate,
    BatchDayOptionRead,
    BatchDayOptionUpdate,
    BatchDayStudentSummary,
    BatchDayTeacherSummary,
    BatchScheduleDayRead,
    BatchScheduleDefaultsRead,
    BatchScheduleDefaultsUpdate,
    StudentBatchScheduleDayRead,
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


class BatchScheduleDayService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_defaults(self) -> BatchScheduleDefaults:
        defaults = await self.session.get(BatchScheduleDefaults, DEFAULTS_ID)
        if defaults is None:
            defaults = BatchScheduleDefaults(
                id=DEFAULTS_ID,
                timezone="UTC",
                default_option_count=3,
                default_teacher_id=None,
                capacity_strategy=BatchCapacityStrategy.BATCH_GROUP_DEFAULT.value,
                fixed_capacity=None,
                option_templates=DEFAULT_TEMPLATES,
            )
            self.session.add(defaults)
            await self.session.commit()
            await self.session.refresh(defaults)
        return defaults

    async def update_defaults(
        self,
        defaults_in: BatchScheduleDefaultsUpdate,
    ) -> BatchScheduleDefaults:
        defaults = await self.get_defaults()
        update_data = defaults_in.model_dump(exclude_unset=True, mode="json")
        for field in (
            "default_option_count",
            "capacity_strategy",
            "option_templates",
        ):
            if field in update_data and update_data[field] is None:
                raise BadRequestError(f"{field} cannot be null")

        teacher_id = update_data.get("default_teacher_id", defaults.default_teacher_id)
        if teacher_id is not None:
            await self._get_active_teacher(teacher_id)

        strategy = update_data.get("capacity_strategy", defaults.capacity_strategy)
        fixed_capacity = update_data.get("fixed_capacity", defaults.fixed_capacity)
        if strategy == BatchCapacityStrategy.FIXED.value and fixed_capacity is None:
            raise BadRequestError("fixed_capacity is required for fixed capacity strategy")
        if strategy == BatchCapacityStrategy.BATCH_GROUP_DEFAULT.value:
            fixed_capacity = None
            update_data["fixed_capacity"] = None

        option_templates = update_data.get("option_templates")
        option_count = update_data.get("default_option_count", defaults.default_option_count)
        effective_templates = option_templates or defaults.option_templates
        if option_count > len(effective_templates):
            raise BadRequestError("default_option_count cannot exceed option template count")

        for field, value in update_data.items():
            setattr(defaults, field, value)
        await self.session.commit()
        await self.session.refresh(defaults)
        return defaults

    async def create_day(self, day_in: BatchDayCreate) -> BatchScheduleDayRead:
        day = await self._create_day(day_in)
        await self.session.commit()
        await self.session.refresh(day)
        return await self.get_day(day.id)

    async def create_days_bulk(
        self,
        bulk_in: BatchDayBulkCreate,
    ) -> BatchDayBulkCreateResult:
        weekdays = {DAY_TO_INDEX[value] for value in bulk_in.weekdays}
        selected_dates: list[date] = []
        current_date = bulk_in.starts_from
        while current_date <= bulk_in.starts_to:
            if current_date.weekday() in weekdays:
                selected_dates.append(current_date)
            current_date += timedelta(days=1)
        if not selected_dates:
            raise BadRequestError("No dates match the selected weekdays")

        created: list[BatchScheduleDay] = []
        for schedule_date in selected_dates:
            options = [
                BatchDayOptionCreate(
                    display_label=option.display_label,
                    starts_at=datetime.combine(
                        schedule_date,
                        option.start_time_utc,
                        tzinfo=UTC,
                    ),
                    ends_at=datetime.combine(
                        schedule_date,
                        option.end_time_utc,
                        tzinfo=UTC,
                    ),
                    teacher_id=option.teacher_id,
                    capacity=option.capacity,
                )
                for option in bulk_in.options
            ]
            try:
                created.append(
                    await self._create_day(
                        BatchDayCreate(
                            batch_group_id=bulk_in.batch_group_id,
                            schedule_date=schedule_date,
                            default_teacher_id=bulk_in.default_teacher_id,
                            actor_user_id=bulk_in.actor_user_id,
                            options=options,
                        )
                    )
                )
            except (BadRequestError, ConflictError, NotFoundError) as exc:
                raise ConflictError(
                    f"Batch-day conflict on {schedule_date.isoformat()}: {exc.detail}"
                ) from exc

        await self.session.commit()
        reads = await self._read_days([day.id for day in created])
        return BatchDayBulkCreateResult(created_count=len(reads), batch_days=reads)

    async def list_days(
        self,
        pagination: PaginationParams,
        *,
        batch_group_id: UUID | None = None,
        starts_from: date | None = None,
        starts_to: date | None = None,
    ) -> Page:
        statement = (
            select(BatchScheduleDay, BatchGroup)
            .join(BatchGroup, BatchGroup.id == BatchScheduleDay.batch_group_id)
            .order_by(BatchScheduleDay.schedule_date.asc(), BatchScheduleDay.id.asc())
        )
        if batch_group_id is not None:
            statement = statement.where(BatchScheduleDay.batch_group_id == batch_group_id)
        if starts_from is not None:
            statement = statement.where(BatchScheduleDay.schedule_date >= starts_from)
        if starts_to is not None:
            statement = statement.where(BatchScheduleDay.schedule_date <= starts_to)
        rows, total = await paginate_rows(self.session, statement, pagination)
        items = await self._read_days(
            [day.id for day, _batch in rows],
            day_rows=rows,
        )
        return Page(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def get_day(self, day_id: UUID) -> BatchScheduleDayRead:
        reads = await self._read_days([day_id])
        if not reads:
            raise NotFoundError("Batch schedule day not found")
        return reads[0]

    async def cancel_day(
        self,
        day_id: UUID,
        action_in: BatchDayActionRequest,
    ) -> BatchScheduleDayRead:
        await self._get_optional_user(action_in.actor_user_id)
        days = await self._lock_days([day_id])
        await self._validate_days_can_be_cancelled(days)
        if days[0].status != BatchScheduleDayStatus.CANCELLED:
            await self._cancel_locked_day(days[0], action_in)
            await self.session.commit()
        return await self.get_day(day_id)

    async def cancel_days_bulk(
        self,
        cancel_in: BatchDayBulkCancelRequest,
    ) -> BatchDayBulkCancelResult:
        await self._get_optional_user(cancel_in.actor_user_id)
        days = await self._lock_days(cancel_in.day_ids)
        await self._validate_days_can_be_cancelled(days)
        already_cancelled_count = sum(
            day.status == BatchScheduleDayStatus.CANCELLED for day in days
        )
        action = BatchDayActionRequest(
            actor_user_id=cancel_in.actor_user_id,
            reason=cancel_in.reason,
        )
        for day in days:
            if day.status != BatchScheduleDayStatus.CANCELLED:
                await self._cancel_locked_day(day, action)
        if already_cancelled_count != len(days):
            await self.session.commit()
        reads = await self._read_days(cancel_in.day_ids)
        return BatchDayBulkCancelResult(
            cancelled_count=len(days) - already_cancelled_count,
            already_cancelled_count=already_cancelled_count,
            batch_days=reads,
        )

    async def list_student_days(
        self,
        student_id: UUID,
        pagination: PaginationParams,
        *,
        starts_from: date | None = None,
        starts_to: date | None = None,
    ) -> Page:
        student = await self.session.get(Student, student_id)
        if student is None:
            raise NotFoundError("Student not found")
        if student.program_type != StudentProgramType.BATCH:
            raise ConflictError("Student is not a batch student")
        membership = await self.session.scalar(
            select(StudentBatchMembership).where(
                StudentBatchMembership.student_id == student.id,
                StudentBatchMembership.is_active.is_(True),
            )
        )
        if membership is None:
            raise ConflictError("Student does not have an active batch membership")
        page = await self.list_days(
            pagination,
            batch_group_id=membership.batch_group_id,
            starts_from=starts_from or datetime.now(UTC).date(),
            starts_to=starts_to,
        )
        day_ids = [day.id for day in page.items]
        selected_rows = (
            await self.session.execute(
                select(
                    ClassSession.batch_schedule_day_id,
                    Booking.id,
                    Booking.class_session_id,
                )
                .join(Booking, Booking.class_session_id == ClassSession.id)
                .where(
                    ClassSession.batch_schedule_day_id.in_(day_ids),
                    Booking.student_id == student.id,
                    Booking.status != BookingStatus.CANCELLED,
                )
            )
        ).all()
        selected = {
            day_id: (booking_id, class_session_id)
            for day_id, booking_id, class_session_id in selected_rows
        }
        now = datetime.now(UTC)
        items = []
        for day in page.items:
            selected_booking_id, selected_session_id = selected.get(day.id, (None, None))
            open_options = [
                option
                for option in day.options
                if day.status == BatchScheduleDayStatus.SCHEDULED
                and option.status == ClassSessionStatus.SCHEDULED
                and option.starts_at > now
                and student.access_starts_at is not None
                and student.access_ends_at is not None
                and student.access_starts_at <= option.starts_at
                and student.access_ends_at > option.starts_at
                and (
                    option.available_capacity > 0
                    or option.id == selected_session_id
                )
            ]
            items.append(
                StudentBatchScheduleDayRead(
                    id=day.id,
                    batch_group_id=day.batch_group_id,
                    batch=day.batch,
                    schedule_date=day.schedule_date,
                    options=open_options,
                    selected_booking_id=selected_booking_id,
                    selected_class_session_id=selected_session_id,
                )
            )
        return Page(
            items=items,
            total=page.total,
            page=page.page,
            page_size=page.page_size,
        )

    async def add_option(
        self,
        day_id: UUID,
        option_in: BatchDayOptionCreate,
    ) -> BatchScheduleDayRead:
        day = await self._get_day_model(day_id)
        if option_in.starts_at.date() != day.schedule_date:
            raise BadRequestError("option starts_at must fall on batch schedule date in UTC")
        sessions = await self._get_day_sessions(day_id)
        if len([value for value in sessions if value.status != ClassSessionStatus.CANCELLED]) >= (
            MAX_BATCH_DAY_OPTIONS
        ):
            raise ConflictError("Batch day already has the maximum number of options")
        await self._validate_option(
            day=day,
            option=option_in,
            existing_sessions=sessions,
        )
        batch_group = await self.session.get(BatchGroup, day.batch_group_id)
        class_session = ClassSession(
            teacher_id=option_in.teacher_id,
            teacher_availability_slot_id=None,
            batch_group_id=day.batch_group_id,
            batch_schedule_day_id=day.id,
            program_type=StudentProgramType.BATCH,
            batch_slot=None,
            display_label=option_in.display_label,
            option_order=max((value.option_order or 0 for value in sessions), default=0) + 1,
            starts_at=option_in.starts_at,
            ends_at=option_in.ends_at,
            status=ClassSessionStatus.SCHEDULED,
            capacity=option_in.capacity or batch_group.default_capacity,
        )
        self.session.add(class_session)
        await self.session.commit()
        return await self.get_day(day.id)

    async def update_option(
        self,
        day_id: UUID,
        class_session_id: UUID,
        option_in: BatchDayOptionUpdate,
    ) -> BatchScheduleDayRead:
        day = await self._get_day_model(day_id)
        await self._get_optional_user(option_in.actor_user_id)
        class_session = await self._get_day_session_for_update(day_id, class_session_id)
        if class_session.status != ClassSessionStatus.SCHEDULED:
            raise ConflictError("Only scheduled options can be updated")
        update_data = option_in.model_dump(
            exclude_unset=True,
            exclude={"reason", "actor_user_id"},
        )
        for field in ("display_label", "starts_at", "ends_at", "capacity"):
            if field in update_data and update_data[field] is None:
                raise BadRequestError(f"{field} cannot be null")
        starts_at = update_data.get("starts_at", class_session.starts_at)
        ends_at = update_data.get("ends_at", class_session.ends_at)
        if starts_at >= ends_at:
            raise BadRequestError("starts_at must be before ends_at")
        if starts_at.date() != day.schedule_date:
            raise BadRequestError("option starts_at must fall on batch schedule date in UTC")
        capacity = update_data.get("capacity", class_session.capacity)
        active_bookings = list(
            await self.session.scalars(
                select(Booking)
                .where(
                    Booking.class_session_id == class_session.id,
                    Booking.status == BookingStatus.BOOKED,
                )
                .with_for_update()
            )
        )
        active_count = len(active_bookings)
        if capacity < active_count:
            raise ConflictError("Capacity cannot be below active booking count")
        teacher_id = update_data.get("teacher_id", class_session.teacher_id)
        if "teacher_id" in option_in.model_fields_set and teacher_id is None:
            pass
        elif teacher_id is not None:
            await self._get_active_teacher(teacher_id)
        candidate = BatchDayOptionCreate(
            display_label=update_data.get("display_label", class_session.display_label),
            starts_at=starts_at,
            ends_at=ends_at,
            teacher_id=teacher_id,
            capacity=capacity,
        )
        await self._validate_option(
            day=day,
            option=candidate,
            existing_sessions=await self._get_day_sessions(day_id),
            exclude_session_id=class_session.id,
        )
        day_start = datetime.combine(starts_at.date(), time.min, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        for booking in active_bookings:
            conflict = await self.session.scalar(
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
            if conflict is not None:
                raise ConflictError(
                    "A booked student already has an active class on the destination UTC date"
                )
        schedule_changed = any(
            field in update_data
            for field in ("starts_at", "ends_at", "teacher_id", "capacity")
        )
        old_metadata = {
            "starts_at": class_session.starts_at.isoformat(),
            "ends_at": class_session.ends_at.isoformat(),
            "teacher_id": str(class_session.teacher_id) if class_session.teacher_id else None,
            "capacity": class_session.capacity,
        }
        new_metadata = {
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "teacher_id": str(teacher_id) if teacher_id else None,
            "capacity": capacity,
        }
        if schedule_changed:
            for booking in active_bookings:
                for event_type in (
                    BookingEventType.RESCHEDULED_FROM,
                    BookingEventType.RESCHEDULED_TO,
                ):
                    self.session.add(
                        BookingEvent(
                            booking_id=booking.id,
                            event_type=event_type,
                            actor_user_id=option_in.actor_user_id,
                            reason=option_in.reason or "batch-day option updated",
                            event_metadata={
                                "source": "admin",
                                "batch_schedule_day_id": str(day.id),
                                "old": old_metadata,
                                "new": new_metadata,
                            },
                        )
                    )
        for field, value in update_data.items():
            setattr(class_session, field, value)
        await self.session.commit()
        return await self.get_day(day.id)

    async def remove_option(
        self,
        day_id: UUID,
        class_session_id: UUID,
    ) -> BatchScheduleDayRead:
        class_session = await self._get_day_session_for_update(day_id, class_session_id)
        if await self._active_booking_count(class_session.id):
            raise ConflictError("Move or remove active students before removing this option")
        class_session.status = ClassSessionStatus.CANCELLED
        await self.session.commit()
        return await self.get_day(day_id)

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
        active_days = [
            day for day in days if day.status != BatchScheduleDayStatus.CANCELLED
        ]
        if not active_days:
            return
        session_rows = list(
            await self.session.scalars(
                select(ClassSession)
                .where(
                    ClassSession.batch_schedule_day_id.in_(
                        [day.id for day in active_days]
                    )
                )
                .order_by(ClassSession.id.asc())
                .with_for_update()
            )
        )
        sessions_by_day = defaultdict(list)
        for class_session in session_rows:
            sessions_by_day[class_session.batch_schedule_day_id].append(class_session)
        for day in active_days:
            sessions = sessions_by_day[day.id]
            if sessions and all(
                value.status == ClassSessionStatus.COMPLETED for value in sessions
            ):
                raise ConflictError(
                    "Completed batch schedule day cannot be cancelled: "
                    f"{day.schedule_date.isoformat()}"
                )
            if not sessions or max(value.ends_at for value in sessions) <= now:
                raise ConflictError(
                    "Past batch schedule day cannot be cancelled: "
                    f"{day.schedule_date.isoformat()}"
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
