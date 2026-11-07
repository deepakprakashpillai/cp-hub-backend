from app.modules.batch_schedule_days.lifecycle_service import BatchScheduleDayLifecycleService
from app.modules.batch_schedule_days.option_service import BatchScheduleOptionService
from app.modules.batch_schedule_days.query_service import BatchScheduleDayQueryService


class _BatchScheduleDayOperations(
    BatchScheduleDayQueryService,
    BatchScheduleDayLifecycleService,
    BatchScheduleOptionService,
):
    """Test-only composite for low-level invariant coverage."""


__all__ = [
    "BatchScheduleDayQueryService",
    "BatchScheduleDayLifecycleService",
    "BatchScheduleOptionService",
]
