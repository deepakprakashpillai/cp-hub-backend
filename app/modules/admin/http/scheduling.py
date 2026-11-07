from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.admin.http.types import (
    AvailabilitySlotSourceQuery,
    AvailabilitySlotStatusQuery,
    DateQuery,
    DatetimeQuery,
    DaysAheadQuery,
    SortOrderQuery,
    TeacherIdQuery,
)
from app.modules.admin.schemas import (
    AdminTeacherAvailabilityGenerationResult,
    SortOrder,
)
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
    BatchScheduleDefaultsRead,
    BatchScheduleDefaultsUpdate,
)
from app.modules.bookings.schemas import (
    BookingRead,
)
from app.modules.read_models.services import (
    AdminBatchScheduleService,
    AdminSchedulingService,
)
from app.modules.schedules.schemas import (
    TeacherAvailabilityBlockCreate,
    TeacherAvailabilityRuleCreate,
    TeacherAvailabilityRuleRead,
    TeacherAvailabilityRuleUpdate,
    TeacherAvailabilitySlotBulkCreate,
    TeacherAvailabilitySlotCreate,
    TeacherAvailabilitySlotRead,
    TeacherAvailabilitySlotUpdate,
)

router = APIRouter()


def normalize_query_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.post(
    "/teachers/{teacher_id}/availability/generate",
    response_model=AdminTeacherAvailabilityGenerationResult,
)
async def generate_teacher_availability_slots(
    teacher_id: UUID,
    session: DBSession,
    days_ahead: DaysAheadQuery = 14,
) -> AdminTeacherAvailabilityGenerationResult:
    result = await AdminSchedulingService(session).generate_teacher_availability_slots(
        teacher_id,
        days_ahead=days_ahead,
    )
    return AdminTeacherAvailabilityGenerationResult(
        rules_checked=result.rules_checked,
        slots_created=result.slots_created,
        slots_cancelled=result.slots_cancelled,
        slots_skipped=result.slots_skipped,
    )


@router.get(
    "/teacher-availability/rules",
    response_model=Page[TeacherAvailabilityRuleRead],
)
async def list_teacher_availability_rules(
    session: DBSession,
    pagination: Pagination,
    teacher_id: TeacherIdQuery = None,
) -> Page[TeacherAvailabilityRuleRead]:
    return await AdminSchedulingService(session).list_teacher_availability_rules(
        pagination,
        teacher_id=teacher_id,
    )


@router.post(
    "/teacher-availability/rules",
    response_model=TeacherAvailabilityRuleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_teacher_availability_rule(
    rule_in: TeacherAvailabilityRuleCreate,
    session: DBSession,
) -> TeacherAvailabilityRuleRead:
    return await AdminSchedulingService(session).create_teacher_availability_rule(rule_in)


@router.get(
    "/teacher-availability/rules/{rule_id}",
    response_model=TeacherAvailabilityRuleRead,
)
async def get_teacher_availability_rule(
    rule_id: UUID,
    session: DBSession,
) -> TeacherAvailabilityRuleRead:
    return await AdminSchedulingService(session).get_teacher_availability_rule(rule_id)


@router.patch(
    "/teacher-availability/rules/{rule_id}",
    response_model=TeacherAvailabilityRuleRead,
)
async def update_teacher_availability_rule(
    rule_id: UUID,
    rule_in: TeacherAvailabilityRuleUpdate,
    session: DBSession,
) -> TeacherAvailabilityRuleRead:
    return await AdminSchedulingService(session).update_teacher_availability_rule(rule_id, rule_in)


@router.delete(
    "/teacher-availability/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_teacher_availability_rule(
    rule_id: UUID,
    session: DBSession,
) -> Response:
    await AdminSchedulingService(session).delete_teacher_availability_rule(rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/teacher-availability/slots",
    response_model=Page[TeacherAvailabilitySlotRead],
)
async def list_teacher_availability_slots(
    session: DBSession,
    pagination: Pagination,
    teacher_id: TeacherIdQuery = None,
    starts_from: DatetimeQuery = None,
    starts_to: DatetimeQuery = None,
    status: AvailabilitySlotStatusQuery = None,
    source: AvailabilitySlotSourceQuery = None,
    sort_order: SortOrderQuery = SortOrder.ASC,
) -> Page[TeacherAvailabilitySlotRead]:
    return await AdminSchedulingService(session).list_teacher_availability_slots(
        pagination,
        teacher_id=teacher_id,
        starts_from=normalize_query_datetime(starts_from),
        starts_to=normalize_query_datetime(starts_to),
        status=status,
        source=source,
        sort_order=sort_order,
    )


@router.post(
    "/teacher-availability/slots",
    response_model=TeacherAvailabilitySlotRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_teacher_availability_slot(
    slot_in: TeacherAvailabilitySlotCreate,
    session: DBSession,
) -> TeacherAvailabilitySlotRead:
    return await AdminSchedulingService(session).create_teacher_availability_slot(slot_in)


@router.post(
    "/teacher-availability/slots/bulk",
    response_model=list[TeacherAvailabilitySlotRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_teacher_availability_slots_bulk(
    slots_in: TeacherAvailabilitySlotBulkCreate,
    session: DBSession,
) -> list[TeacherAvailabilitySlotRead]:
    return await AdminSchedulingService(session).create_teacher_availability_slots_bulk(slots_in)


@router.post(
    "/teacher-availability/blocks",
    response_model=TeacherAvailabilitySlotRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_teacher_availability_block(
    block_in: TeacherAvailabilityBlockCreate,
    session: DBSession,
) -> TeacherAvailabilitySlotRead:
    return await AdminSchedulingService(session).create_teacher_availability_block(block_in)


@router.get(
    "/teacher-availability/slots/{slot_id}",
    response_model=TeacherAvailabilitySlotRead,
)
async def get_teacher_availability_slot(
    slot_id: UUID,
    session: DBSession,
) -> TeacherAvailabilitySlotRead:
    return await AdminSchedulingService(session).get_teacher_availability_slot(slot_id)


@router.patch(
    "/teacher-availability/slots/{slot_id}",
    response_model=TeacherAvailabilitySlotRead,
)
async def update_teacher_availability_slot(
    slot_id: UUID,
    slot_in: TeacherAvailabilitySlotUpdate,
    session: DBSession,
) -> TeacherAvailabilitySlotRead:
    return await AdminSchedulingService(session).update_teacher_availability_slot(slot_id, slot_in)


@router.delete(
    "/teacher-availability/slots/{slot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_teacher_availability_slot(
    slot_id: UUID,
    session: DBSession,
) -> Response:
    await AdminSchedulingService(session).delete_teacher_availability_slot(slot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/batch-schedule-defaults",
    response_model=BatchScheduleDefaultsRead,
)
async def get_batch_schedule_defaults(session: DBSession) -> BatchScheduleDefaultsRead:
    return await AdminBatchScheduleService(session).get_batch_schedule_defaults()


@router.patch(
    "/batch-schedule-defaults",
    response_model=BatchScheduleDefaultsRead,
)
async def update_batch_schedule_defaults(
    defaults_in: BatchScheduleDefaultsUpdate,
    session: DBSession,
) -> BatchScheduleDefaultsRead:
    return await AdminBatchScheduleService(session).update_batch_schedule_defaults(defaults_in)


@router.get("/batch-schedule-days", response_model=Page[BatchScheduleDayRead])
async def list_batch_schedule_days(
    session: DBSession,
    pagination: Pagination,
    batch_group_id: UUID | None = None,
    starts_from: DateQuery = None,
    starts_to: DateQuery = None,
) -> Page[BatchScheduleDayRead]:
    return await AdminBatchScheduleService(session).list_batch_schedule_days(
        pagination,
        batch_group_id=batch_group_id,
        starts_from=starts_from,
        starts_to=starts_to,
    )


@router.post(
    "/batch-schedule-days",
    response_model=BatchScheduleDayRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_batch_schedule_day(
    day_in: BatchDayCreate,
    session: DBSession,
) -> BatchScheduleDayRead:
    return await AdminBatchScheduleService(session).create_batch_schedule_day(day_in)


@router.post(
    "/batch-schedule-days/bulk",
    response_model=BatchDayBulkCreateResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_batch_schedule_days_bulk(
    bulk_in: BatchDayBulkCreate,
    session: DBSession,
) -> BatchDayBulkCreateResult:
    return await AdminBatchScheduleService(session).create_batch_schedule_days_bulk(bulk_in)


@router.post(
    "/batch-schedule-days/cancel-bulk",
    response_model=BatchDayBulkCancelResult,
)
async def cancel_batch_schedule_days_bulk(
    cancel_in: BatchDayBulkCancelRequest,
    session: DBSession,
) -> BatchDayBulkCancelResult:
    return await AdminBatchScheduleService(session).cancel_batch_schedule_days_bulk(cancel_in)


@router.get(
    "/batch-schedule-days/{day_id}",
    response_model=BatchScheduleDayRead,
)
async def get_batch_schedule_day(
    day_id: UUID,
    session: DBSession,
) -> BatchScheduleDayRead:
    return await AdminBatchScheduleService(session).get_batch_schedule_day(day_id)


@router.post(
    "/batch-schedule-days/{day_id}/cancel",
    response_model=BatchScheduleDayRead,
)
async def cancel_batch_schedule_day(
    day_id: UUID,
    action_in: BatchDayActionRequest,
    session: DBSession,
) -> BatchScheduleDayRead:
    return await AdminBatchScheduleService(session).cancel_batch_schedule_day(day_id, action_in)


@router.post(
    "/batch-schedule-days/{day_id}/options",
    response_model=BatchScheduleDayRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_batch_schedule_day_option(
    day_id: UUID,
    option_in: BatchDayOptionCreate,
    session: DBSession,
) -> BatchScheduleDayRead:
    return await AdminBatchScheduleService(session).add_batch_schedule_day_option(day_id, option_in)


@router.patch(
    "/batch-schedule-days/{day_id}/options/{class_session_id}",
    response_model=BatchScheduleDayRead,
)
async def update_batch_schedule_day_option(
    day_id: UUID,
    class_session_id: UUID,
    option_in: BatchDayOptionUpdate,
    session: DBSession,
) -> BatchScheduleDayRead:
    return await AdminBatchScheduleService(session).update_batch_schedule_day_option(
        day_id,
        class_session_id,
        option_in,
    )


@router.delete(
    "/batch-schedule-days/{day_id}/options/{class_session_id}",
    response_model=BatchScheduleDayRead,
)
async def remove_batch_schedule_day_option(
    day_id: UUID,
    class_session_id: UUID,
    session: DBSession,
) -> BatchScheduleDayRead:
    return await AdminBatchScheduleService(session).remove_batch_schedule_day_option(
        day_id,
        class_session_id,
    )


@router.put(
    "/batch-schedule-days/{day_id}/students/{student_id}",
    response_model=BatchDayAllocationResult,
)
async def assign_batch_day_student(
    day_id: UUID,
    student_id: UUID,
    allocation_in: BatchDayAllocationRequest,
    session: DBSession,
) -> BatchDayAllocationResult:
    return await AdminBatchScheduleService(session).assign_batch_day_student(
        day_id,
        student_id,
        allocation_in,
    )


@router.delete(
    "/batch-schedule-days/{day_id}/students/{student_id}",
    response_model=BookingRead,
)
async def remove_batch_day_student(
    day_id: UUID,
    student_id: UUID,
    action_in: BatchDayActionRequest,
    session: DBSession,
) -> BookingRead:
    return await AdminBatchScheduleService(session).remove_batch_day_student(
        day_id,
        student_id,
        action_in,
    )
