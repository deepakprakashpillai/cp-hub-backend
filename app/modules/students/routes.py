from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DBSession
from app.modules.students.schemas import (
    StudentCreate,
    StudentProgramChangeRead,
    StudentProgramSwitch,
    StudentRead,
    StudentUpdate,
)
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


@router.get("/program-changes", response_model=list[StudentProgramChangeRead])
async def list_student_program_changes(
    session: DBSession,
    student_id: UUID | None = None,
) -> list[StudentProgramChangeRead]:
    return await StudentService(session).list_program_changes(student_id=student_id)


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
