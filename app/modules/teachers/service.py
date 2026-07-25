from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_scalars
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
from app.modules.teachers.schemas import TeacherCreate, TeacherUpdate
from app.modules.users.models import User
from app.shared.enums import UserRole


class TeacherService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_teachers(self, pagination: PaginationParams) -> Page:
        return await paginate_scalars(
            self.session,
            select(Teacher).order_by(Teacher.created_at.desc()),
            pagination,
        )

    async def get_teacher(self, teacher_id: UUID) -> Teacher:
        teacher = await self.session.get(Teacher, teacher_id)
        if teacher is None:
            raise NotFoundError("Teacher not found")
        return teacher

    async def create_teacher(self, teacher_in: TeacherCreate, *, commit: bool = True) -> Teacher:
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
        if commit:
            await self.session.commit()
            await self.session.refresh(teacher)
        else:
            await self.session.flush()
        return teacher

    async def update_teacher(self, teacher_id: UUID, teacher_in: TeacherUpdate) -> Teacher:
        teacher = await self.get_teacher(teacher_id)
        update_data = teacher_in.model_dump(exclude_unset=True)

        for non_nullable_field in ("display_name", "is_active"):
            if non_nullable_field in update_data and update_data[non_nullable_field] is None:
                raise BadRequestError(f"{non_nullable_field} cannot be null")

        for field, value in update_data.items():
            setattr(teacher, field, value)

        if update_data.get("is_active") is False:
            await self.session.execute(
                update(Student)
                .where(Student.assigned_teacher_id == teacher.id)
                .values(assigned_teacher_id=None)
            )

        await self.session.commit()
        await self.session.refresh(teacher)
        return teacher
