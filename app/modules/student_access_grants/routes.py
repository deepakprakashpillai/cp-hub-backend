from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.student_access_grants.schemas import (
    StudentAccessGrantCreate,
    StudentAccessGrantRead,
)
from app.modules.student_access_grants.service import StudentAccessGrantService

router = APIRouter()


@router.get("", response_model=Page[StudentAccessGrantRead])
async def list_student_access_grants(
    session: DBSession,
    pagination: Pagination,
    student_id: UUID | None = None,
) -> Page[StudentAccessGrantRead]:
    return await StudentAccessGrantService(session).list_grants(
        pagination,
        student_id=student_id,
    )


@router.post("", response_model=StudentAccessGrantRead, status_code=status.HTTP_201_CREATED)
async def create_student_access_grant(
    grant_in: StudentAccessGrantCreate,
    session: DBSession,
) -> StudentAccessGrantRead:
    return await StudentAccessGrantService(session).create_grant(grant_in)


@router.get("/{grant_id}", response_model=StudentAccessGrantRead)
async def get_student_access_grant(
    grant_id: UUID,
    session: DBSession,
) -> StudentAccessGrantRead:
    return await StudentAccessGrantService(session).get_grant(grant_id)
