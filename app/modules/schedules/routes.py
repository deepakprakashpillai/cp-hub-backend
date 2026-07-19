from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DBSession
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
from app.modules.schedules.service import ScheduleService

router = APIRouter()
TeacherIdQuery = Annotated[UUID | None, Query()]
DatetimeQuery = Annotated[datetime | None, Query()]


def normalize_query_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.get("/teacher-availability/rules", response_model=list[TeacherAvailabilityRuleRead])
async def list_teacher_availability_rules(
    session: DBSession,
    teacher_id: TeacherIdQuery = None,
) -> list[TeacherAvailabilityRuleRead]:
    return await ScheduleService(session).list_teacher_availability_rules(teacher_id)


@router.post(
    "/teacher-availability/rules",
    response_model=TeacherAvailabilityRuleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_teacher_availability_rule(
    rule_in: TeacherAvailabilityRuleCreate,
    session: DBSession,
) -> TeacherAvailabilityRuleRead:
    return await ScheduleService(session).create_teacher_availability_rule(rule_in)


@router.get("/teacher-availability/rules/{rule_id}", response_model=TeacherAvailabilityRuleRead)
async def get_teacher_availability_rule(
    rule_id: UUID,
    session: DBSession,
) -> TeacherAvailabilityRuleRead:
    return await ScheduleService(session).get_teacher_availability_rule(rule_id)


@router.patch("/teacher-availability/rules/{rule_id}", response_model=TeacherAvailabilityRuleRead)
async def update_teacher_availability_rule(
    rule_id: UUID,
    rule_in: TeacherAvailabilityRuleUpdate,
    session: DBSession,
) -> TeacherAvailabilityRuleRead:
    return await ScheduleService(session).update_teacher_availability_rule(rule_id, rule_in)


@router.delete("/teacher-availability/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_teacher_availability_rule(
    rule_id: UUID,
    session: DBSession,
) -> Response:
    await ScheduleService(session).delete_teacher_availability_rule(rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/teacher-availability/slots", response_model=list[TeacherAvailabilitySlotRead])
async def list_teacher_availability_slots(
    session: DBSession,
    teacher_id: TeacherIdQuery = None,
    starts_from: DatetimeQuery = None,
    starts_to: DatetimeQuery = None,
) -> list[TeacherAvailabilitySlotRead]:
    return await ScheduleService(session).list_teacher_availability_slots(
        teacher_id=teacher_id,
        starts_from=normalize_query_datetime(starts_from),
        starts_to=normalize_query_datetime(starts_to),
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
    return await ScheduleService(session).create_teacher_availability_slot(slot_in)


@router.post(
    "/teacher-availability/slots/bulk",
    response_model=list[TeacherAvailabilitySlotRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_teacher_availability_slots_bulk(
    slots_in: TeacherAvailabilitySlotBulkCreate,
    session: DBSession,
) -> list[TeacherAvailabilitySlotRead]:
    return await ScheduleService(session).create_teacher_availability_slots_bulk(slots_in)


@router.post(
    "/teacher-availability/blocks",
    response_model=TeacherAvailabilitySlotRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_teacher_availability_block(
    block_in: TeacherAvailabilityBlockCreate,
    session: DBSession,
) -> TeacherAvailabilitySlotRead:
    return await ScheduleService(session).create_teacher_availability_block(block_in)


@router.get("/teacher-availability/slots/{slot_id}", response_model=TeacherAvailabilitySlotRead)
async def get_teacher_availability_slot(
    slot_id: UUID,
    session: DBSession,
) -> TeacherAvailabilitySlotRead:
    return await ScheduleService(session).get_teacher_availability_slot(slot_id)


@router.patch("/teacher-availability/slots/{slot_id}", response_model=TeacherAvailabilitySlotRead)
async def update_teacher_availability_slot(
    slot_id: UUID,
    slot_in: TeacherAvailabilitySlotUpdate,
    session: DBSession,
) -> TeacherAvailabilitySlotRead:
    return await ScheduleService(session).update_teacher_availability_slot(slot_id, slot_in)


@router.delete("/teacher-availability/slots/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_teacher_availability_slot(
    slot_id: UUID,
    session: DBSession,
) -> Response:
    await ScheduleService(session).delete_teacher_availability_slot(slot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
