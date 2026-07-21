from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.schemas import AdminStudentCreate, AdminTeacherCreate
from app.modules.students.models import Student
from app.modules.students.schemas import StudentCreate
from app.modules.students.service import StudentService
from app.modules.teachers.models import Teacher
from app.modules.teachers.schemas import TeacherCreate
from app.modules.teachers.service import TeacherService
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate
from app.modules.users.service import UserService
from app.shared.enums import UserRole


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_teacher(self, teacher_in: AdminTeacherCreate) -> tuple[User, Teacher]:
        user = await UserService(self.session).create_user(
            UserCreate(
                full_name=teacher_in.full_name,
                email=teacher_in.email,
                phone=teacher_in.phone,
                role=UserRole.TEACHER,
                is_active=teacher_in.is_active,
            ),
            commit=False,
        )
        teacher = await TeacherService(self.session).create_teacher(
            TeacherCreate(
                user_id=user.id,
                display_name=teacher_in.display_name,
                bio=teacher_in.bio,
                profile_photo_url=teacher_in.profile_photo_url,
            ),
            commit=False,
        )

        await self.session.commit()
        await self.session.refresh(user)
        await self.session.refresh(teacher)
        return user, teacher

    async def create_student(self, student_in: AdminStudentCreate) -> tuple[User, Student]:
        user = await UserService(self.session).create_user(
            UserCreate(
                full_name=student_in.full_name,
                email=student_in.email,
                phone=student_in.phone,
                role=UserRole.STUDENT,
                is_active=student_in.is_active,
            ),
            commit=False,
        )
        student = await StudentService(self.session).create_student(
            StudentCreate(
                user_id=user.id,
                program_type=student_in.program_type,
                status=student_in.status,
                access_starts_at=student_in.access_starts_at,
                access_ends_at=student_in.access_ends_at,
                notes=student_in.notes,
            ),
            commit=False,
        )

        await self.session.commit()
        await self.session.refresh(user)
        await self.session.refresh(student)
        return user, student
