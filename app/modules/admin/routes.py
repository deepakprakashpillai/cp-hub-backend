from fastapi import APIRouter, status

from app.api.deps import DBSession
from app.modules.admin.schemas import (
    AdminStudentCreate,
    AdminStudentRead,
    AdminTeacherCreate,
    AdminTeacherRead,
)
from app.modules.admin.service import AdminService

router = APIRouter()


@router.post("/teachers", response_model=AdminTeacherRead, status_code=status.HTTP_201_CREATED)
async def create_teacher(
    teacher_in: AdminTeacherCreate,
    session: DBSession,
) -> AdminTeacherRead:
    user, teacher = await AdminService(session).create_teacher(teacher_in)
    return AdminTeacherRead(user=user, teacher=teacher)


@router.post("/students", response_model=AdminStudentRead, status_code=status.HTTP_201_CREATED)
async def create_student(
    student_in: AdminStudentCreate,
    session: DBSession,
) -> AdminStudentRead:
    user, student = await AdminService(session).create_student(student_in)
    return AdminStudentRead(user=user, student=student)
