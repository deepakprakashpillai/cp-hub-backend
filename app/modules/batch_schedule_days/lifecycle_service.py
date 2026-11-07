from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.batch_schedule_days._shared import _BatchScheduleDayShared
from app.modules.batch_schedule_days.models import (
    BatchScheduleDay,
    BatchScheduleDefaults,
)
from app.modules.batch_schedule_days.query_service import BatchScheduleDayQueryService
from app.modules.batch_schedule_days.schemas import (
    BatchDayActionRequest,
    BatchDayBulkCancelRequest,
    BatchDayBulkCancelResult,
    BatchDayBulkCreate,
    BatchDayBulkCreateResult,
    BatchDayCreate,
    BatchDayOptionCreate,
    BatchScheduleDayRead,
    BatchScheduleDefaultsUpdate,
)
from app.shared.enums import (
    BatchCapacityStrategy,
    BatchScheduleDayStatus,
    DayOfWeek,
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


class BatchScheduleDayLifecycleService(_BatchScheduleDayShared):
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
        return await BatchScheduleDayQueryService(self.session).get_day(day.id)

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
        return await BatchScheduleDayQueryService(self.session).get_day(day_id)

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
