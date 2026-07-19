from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.teachers.models import Teacher
from app.modules.teachers.schemas import TeacherCreate
from app.modules.users.models import User
from app.shared.enums import UserRole


class TeacherService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_teachers(self) -> list[Teacher]:
        result = await self.session.scalars(select(Teacher).order_by(Teacher.created_at.desc()))
        return list(result)

    async def get_teacher(self, teacher_id: UUID) -> Teacher:
        teacher = await self.session.get(Teacher, teacher_id)
        if teacher is None:
            raise NotFoundError("Teacher not found")
        return teacher

    async def create_teacher(self, teacher_in: TeacherCreate) -> Teacher:
        user = await self.session.get(User, teacher_in.user_id)
        if user is None:
            raise NotFoundError("User not found")

        if user.role != UserRole.TEACHER:
            raise ConflictError("Teacher profile can only be created for a teacher user")

        existing_teacher = await self.session.scalar(
            select(Teacher).where(Teacher.user_id == teacher_in.user_id)
        )
        if existing_teacher is not None:
            raise ConflictError("Teacher profile already exists for this user")

        teacher = Teacher(**teacher_in.model_dump())
        self.session.add(teacher)
        await self.session.commit()
        await self.session.refresh(teacher)
        return teacher
