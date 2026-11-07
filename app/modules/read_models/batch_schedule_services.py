from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, PaginationParams
from app.modules.batch_schedule_days.schemas import (
    BatchDayActionRequest,
    BatchDayAllocationRequest,
    BatchDayAllocationResult,
    BatchDayBulkCancelRequest,
    BatchDayBulkCancelResult,
    BatchDayBulkCreate,
    BatchDayBulkCreateResult,
    BatchDayCreate,
    BatchDayOptionCreate,
    BatchDayOptionUpdate,
    BatchScheduleDayRead,
    BatchScheduleDefaultsUpdate,
)
from app.modules.batch_schedule_days.service import (
    BatchScheduleDayLifecycleService,
    BatchScheduleDayQueryService,
    BatchScheduleOptionService,
)
from app.modules.bookings.models import Booking
from app.modules.bookings.service import (
    BookingCreationService,
)
from app.modules.read_models.admin_schemas import (
    AdminStudentAccessState,
)
from app.modules.students.models import Student


class _ServiceBase:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


class AdminBatchScheduleService(_ServiceBase):
    async def get_batch_schedule_defaults(self):
        return await BatchScheduleDayLifecycleService(self.session).get_defaults()

    async def update_batch_schedule_defaults(self, defaults_in: BatchScheduleDefaultsUpdate):
        return await BatchScheduleDayLifecycleService(self.session).update_defaults(defaults_in)

    async def create_batch_schedule_day(
        self,
        day_in: BatchDayCreate,
    ) -> BatchScheduleDayRead:
        return await BatchScheduleDayLifecycleService(self.session).create_day(day_in)

    async def create_batch_schedule_days_bulk(
        self,
        bulk_in: BatchDayBulkCreate,
    ) -> BatchDayBulkCreateResult:
        return await BatchScheduleDayLifecycleService(self.session).create_days_bulk(bulk_in)

    async def list_batch_schedule_days(
        self,
        pagination: PaginationParams,
        *,
        batch_group_id: UUID | None = None,
        starts_from=None,
        starts_to=None,
    ) -> Page:
        return await BatchScheduleDayQueryService(self.session).list_days(
            pagination,
            batch_group_id=batch_group_id,
            starts_from=starts_from,
            starts_to=starts_to,
        )

    async def get_batch_schedule_day(self, day_id: UUID) -> BatchScheduleDayRead:
        return await BatchScheduleDayQueryService(self.session).get_day(day_id)

    async def cancel_batch_schedule_day(
        self,
        day_id: UUID,
        action_in: BatchDayActionRequest,
    ) -> BatchScheduleDayRead:
        return await BatchScheduleDayLifecycleService(self.session).cancel_day(day_id, action_in)

    async def cancel_batch_schedule_days_bulk(
        self,
        cancel_in: BatchDayBulkCancelRequest,
    ) -> BatchDayBulkCancelResult:
        return await BatchScheduleDayLifecycleService(self.session).cancel_days_bulk(cancel_in)

    async def add_batch_schedule_day_option(
        self,
        day_id: UUID,
        option_in: BatchDayOptionCreate,
    ) -> BatchScheduleDayRead:
        return await BatchScheduleOptionService(self.session).add_option(day_id, option_in)

    async def update_batch_schedule_day_option(
        self,
        day_id: UUID,
        class_session_id: UUID,
        option_in: BatchDayOptionUpdate,
    ) -> BatchScheduleDayRead:
        return await BatchScheduleOptionService(self.session).update_option(
            day_id,
            class_session_id,
            option_in,
        )

    async def remove_batch_schedule_day_option(
        self,
        day_id: UUID,
        class_session_id: UUID,
    ) -> BatchScheduleDayRead:
        return await BatchScheduleOptionService(self.session).remove_option(
            day_id,
            class_session_id,
        )

    async def assign_batch_day_student(
        self,
        day_id: UUID,
        student_id: UUID,
        allocation_in: BatchDayAllocationRequest,
    ) -> BatchDayAllocationResult:
        booking, moved_from = await BookingCreationService(self.session).select_batch_day_option(
            student_id=student_id,
            batch_schedule_day_id=day_id,
            class_session_id=allocation_in.class_session_id,
            admin_override=True,
            actor_user_id=allocation_in.actor_user_id,
            reason=allocation_in.reason,
        )
        return BatchDayAllocationResult(
            booking=booking,
            moved_from_booking_id=moved_from,
        )

    async def remove_batch_day_student(
        self,
        day_id: UUID,
        student_id: UUID,
        action_in: BatchDayActionRequest,
    ) -> Booking:
        return await BookingCreationService(self.session).remove_batch_day_selection(
            student_id=student_id,
            batch_schedule_day_id=day_id,
            actor_user_id=action_in.actor_user_id,
            reason=action_in.reason,
        )


def _resolve_dashboard_window(
    *,
    starts_from: datetime | None,
    starts_to: datetime | None,
    now: datetime,
) -> tuple[datetime, datetime]:
    if starts_from is None:
        starts_from = datetime.combine(now.date(), time.min, tzinfo=UTC)
    if starts_to is None:
        starts_to = starts_from + timedelta(days=1)
    if starts_from >= starts_to:
        raise ValueError("starts_from must be before starts_to")
    return starts_from, starts_to


def _normalize_search_query(q: str | None) -> str | None:
    if q is None:
        return None
    normalized = q.strip()
    return normalized or None


def _model_values(model) -> dict:
    return {key: value for key, value in vars(model).items() if not key.startswith("_")}


def _student_access_state_clause(access_state: AdminStudentAccessState, now: datetime):
    if access_state == AdminStudentAccessState.VALID:
        return (
            Student.access_starts_at.is_not(None)
            & (Student.access_starts_at <= now)
            & Student.access_ends_at.is_not(None)
            & (Student.access_ends_at > now)
        )
    if access_state == AdminStudentAccessState.EXPIRED:
        return Student.access_ends_at.is_not(None) & (Student.access_ends_at <= now)
    if access_state == AdminStudentAccessState.NOT_STARTED:
        return Student.access_starts_at.is_not(None) & (Student.access_starts_at > now)
    return or_(Student.access_starts_at.is_(None), Student.access_ends_at.is_(None))
