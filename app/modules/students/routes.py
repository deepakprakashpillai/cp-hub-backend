from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DBSession
from app.modules.students.schemas import StudentCreate, StudentRead, StudentUpdate
from app.modules.students.service import StudentService

router = APIRouter()


@router.get("", response_model=list[StudentRead])
async def list_students(session: DBSession) -> list[StudentRead]:
    return await StudentService(session).list_students()


@router.post("", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
async def create_student(
    student_in: StudentCreate,
    session: DBSession,
) -> StudentRead:
    return await StudentService(session).create_student(student_in)


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
