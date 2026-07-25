from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.batch_groups.schemas import StudentBatchMembershipRead, StudentBatchTransfer
from app.modules.batch_groups.service import BatchGroupService
from app.modules.batch_schedule_days.schemas import (
    BatchDayAllocationResult,
    BatchDayStudentSelection,
    StudentBatchScheduleDayRead,
)
from app.modules.batch_schedule_days.service import BatchScheduleDayService
from app.modules.bookings.service import BookingService
from app.modules.students.schemas import (
    StudentCreate,
    StudentProgramChangeRead,
    StudentProgramSwitch,
    StudentRead,
    StudentUpdate,
)
from app.modules.students.service import StudentService

router = APIRouter()
DateQuery = Annotated[date | None, Query()]


@router.get("", response_model=Page[StudentRead])
async def list_students(session: DBSession, pagination: Pagination) -> Page[StudentRead]:
    return await StudentService(session).list_students(pagination)


@router.post("", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
async def create_student(
    student_in: StudentCreate,
    session: DBSession,
) -> StudentRead:
    return await StudentService(session).create_student(student_in)


@router.get("/program-changes", response_model=Page[StudentProgramChangeRead])
async def list_student_program_changes(
    session: DBSession,
    pagination: Pagination,
    student_id: UUID | None = None,
) -> Page[StudentProgramChangeRead]:
    return await StudentService(session).list_program_changes(
        pagination,
        student_id=student_id,
    )


@router.get("/{student_id}", response_model=StudentRead)
async def get_student(
    student_id: UUID,
    session: DBSession,
) -> StudentRead:
    return await StudentService(session).get_student(student_id)


@router.patch("/{student_id}", response_model=StudentRead)
async def update_student(
    student_id: UUID,
    student_in: StudentUpdate,
    session: DBSession,
) -> StudentRead:
    return await StudentService(session).update_student(student_id, student_in)


@router.post("/{student_id}/program-switch", response_model=StudentProgramChangeRead)
async def switch_student_program(
    student_id: UUID,
    switch_in: StudentProgramSwitch,
    session: DBSession,
) -> StudentProgramChangeRead:
    return await StudentService(session).switch_program(student_id, switch_in)


@router.post("/{student_id}/batch-transfer", response_model=StudentBatchMembershipRead)
async def transfer_student_batch_group(
    student_id: UUID,
    transfer_in: StudentBatchTransfer,
    session: DBSession,
) -> StudentBatchMembershipRead:
    return await BatchGroupService(session).transfer_student_batch_group(student_id, transfer_in)


@router.get("/{student_id}/batch-memberships", response_model=Page[StudentBatchMembershipRead])
async def list_student_batch_memberships(
    student_id: UUID,
    session: DBSession,
    pagination: Pagination,
) -> Page[StudentBatchMembershipRead]:
    return await BatchGroupService(session).list_student_batch_memberships(
        student_id,
        pagination,
    )


@router.get(
    "/{student_id}/batch-schedule-days",
    response_model=Page[StudentBatchScheduleDayRead],
)
async def list_student_batch_schedule_days(
    student_id: UUID,
    session: DBSession,
    pagination: Pagination,
    starts_from: DateQuery = None,
    starts_to: DateQuery = None,
) -> Page[StudentBatchScheduleDayRead]:
    return await BatchScheduleDayService(session).list_student_days(
        student_id,
        pagination,
        starts_from=starts_from,
        starts_to=starts_to,
    )


@router.put(
    "/{student_id}/batch-schedule-days/{day_id}/selection",
    response_model=BatchDayAllocationResult,
)
async def select_student_batch_day_option(
    student_id: UUID,
    day_id: UUID,
    selection_in: BatchDayStudentSelection,
    session: DBSession,
) -> BatchDayAllocationResult:
    booking, moved_from = await BookingService(session).select_batch_day_option(
        student_id=student_id,
        batch_schedule_day_id=day_id,
        class_session_id=selection_in.class_session_id,
        admin_override=False,
        actor_user_id=None,
        reason=selection_in.reason,
    )
    return BatchDayAllocationResult(
        booking=booking,
        moved_from_booking_id=moved_from,
    )
