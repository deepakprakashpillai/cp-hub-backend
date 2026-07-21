from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.teachers.schemas import TeacherCreate, TeacherRead
from app.modules.teachers.service import TeacherService

router = APIRouter()


@router.get("", response_model=Page[TeacherRead])
async def list_teachers(session: DBSession, pagination: Pagination) -> Page[TeacherRead]:
    return await TeacherService(session).list_teachers(pagination)


@router.post("", response_model=TeacherRead, status_code=status.HTTP_201_CREATED)
async def create_teacher(
    teacher_in: TeacherCreate,
    session: DBSession,
) -> TeacherRead:
    return await TeacherService(session).create_teacher(teacher_in)


@router.get("/{teacher_id}", response_model=TeacherRead)
async def get_teacher(
    teacher_id: UUID,
    session: DBSession,
) -> TeacherRead:
    return await TeacherService(session).get_teacher(teacher_id)
