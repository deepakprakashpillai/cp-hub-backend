from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import DBSession
from app.modules.batch_groups.schemas import (
    BatchGroupCreate,
    BatchGroupRead,
    BatchGroupUpdate,
    BatchSessionBulkGenerate,
    BatchSessionBulkGenerateResult,
    StudentBatchMembershipAssign,
    StudentBatchMembershipRead,
)
from app.modules.batch_groups.service import BatchGroupService

router = APIRouter()
IsActiveQuery = Annotated[bool | None, Query()]


@router.get("", response_model=list[BatchGroupRead])
async def list_batch_groups(
    session: DBSession,
    is_active: IsActiveQuery = None,
) -> list[BatchGroupRead]:
    return await BatchGroupService(session).list_batch_groups(is_active=is_active)


@router.post("", response_model=BatchGroupRead, status_code=status.HTTP_201_CREATED)
async def create_batch_group(
    batch_group_in: BatchGroupCreate,
    session: DBSession,
) -> BatchGroupRead:
    return await BatchGroupService(session).create_batch_group(batch_group_in)


@router.get("/{batch_group_id}", response_model=BatchGroupRead)
async def get_batch_group(
    batch_group_id: UUID,
    session: DBSession,
) -> BatchGroupRead:
    return await BatchGroupService(session).get_batch_group(batch_group_id)


@router.patch("/{batch_group_id}", response_model=BatchGroupRead)
async def update_batch_group(
    batch_group_id: UUID,
    batch_group_in: BatchGroupUpdate,
    session: DBSession,
) -> BatchGroupRead:
    return await BatchGroupService(session).update_batch_group(batch_group_id, batch_group_in)


@router.post("/{batch_group_id}/void", response_model=BatchGroupRead)
async def void_batch_group(
    batch_group_id: UUID,
    session: DBSession,
) -> BatchGroupRead:
    return await BatchGroupService(session).void_batch_group(batch_group_id)


@router.get("/{batch_group_id}/students", response_model=list[StudentBatchMembershipRead])
async def list_batch_group_students(
    batch_group_id: UUID,
    session: DBSession,
    is_active: IsActiveQuery = True,
) -> list[StudentBatchMembershipRead]:
    return await BatchGroupService(session).list_batch_group_students(
        batch_group_id=batch_group_id,
        is_active=is_active,
    )


@router.post(
    "/{batch_group_id}/students",
    response_model=StudentBatchMembershipRead,
    status_code=status.HTTP_201_CREATED,
)
async def assign_student_to_batch_group(
    batch_group_id: UUID,
    membership_in: StudentBatchMembershipAssign,
    session: DBSession,
) -> StudentBatchMembershipRead:
    return await BatchGroupService(session).assign_student_to_batch_group(
        batch_group_id,
        membership_in,
    )


@router.post("/{batch_group_id}/sessions/generate", response_model=BatchSessionBulkGenerateResult)
async def generate_batch_sessions(
    batch_group_id: UUID,
    generation_in: BatchSessionBulkGenerate,
    session: DBSession,
) -> BatchSessionBulkGenerateResult:
    class_sessions = await BatchGroupService(session).generate_batch_sessions(
        batch_group_id,
        generation_in,
    )
    return BatchSessionBulkGenerateResult(
        created_count=len(class_sessions),
        class_sessions=class_sessions,
    )

