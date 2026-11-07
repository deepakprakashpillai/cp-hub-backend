from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_rows
from app.modules.batch_groups.models import BatchGroup, StudentBatchMembership
from app.modules.batch_schedule_days._shared import _BatchScheduleDayShared
from app.modules.batch_schedule_days.models import (
    BatchScheduleDay,
)
from app.modules.batch_schedule_days.schemas import (
    BatchScheduleDayRead,
    StudentBatchScheduleDayRead,
)
from app.modules.bookings.models import Booking
from app.modules.classes.models import ClassSession
from app.modules.students.models import Student
from app.shared.enums import (
    BatchScheduleDayStatus,
    BookingStatus,
    ClassSessionStatus,
    DayOfWeek,
    StudentProgramType,
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


class BatchScheduleDayQueryService(_BatchScheduleDayShared):
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
                and (option.available_capacity > 0 or option.id == selected_session_id)
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
