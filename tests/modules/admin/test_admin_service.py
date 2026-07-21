from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.admin.schemas import AdminStudentCreate, AdminTeacherCreate
from app.modules.admin.service import AdminService
from app.modules.students.models import Student
from app.modules.students.service import StudentService
from app.modules.teachers.models import Teacher
from app.modules.teachers.service import TeacherService
from app.modules.users.models import User
from app.modules.users.service import UserService
from app.shared.enums import StudentProgramType, StudentStatus, UserRole


class FakeSession:
    def __init__(self) -> None:
        self.commit = AsyncMock()
        self.refresh = AsyncMock()


def test_admin_student_create_normalizes_access_datetimes_to_utc() -> None:
    student = AdminStudentCreate(
        full_name="Student One",
        email="student@example.com",
        program_type=StudentProgramType.ONE_ON_ONE,
        access_starts_at=datetime.fromisoformat("2026-07-20T00:00:00+05:30"),
        access_ends_at=datetime.fromisoformat("2026-08-19T00:00:00+05:30"),
    )

    assert student.is_active is True
    assert student.status == StudentStatus.ENROLLED
    assert student.access_starts_at == datetime(2026, 7, 19, 18, 30, tzinfo=UTC)
    assert student.access_ends_at == datetime(2026, 8, 18, 18, 30, tzinfo=UTC)


def test_admin_student_create_rejects_naive_access_datetime() -> None:
    with pytest.raises(ValidationError, match="datetime must include timezone info"):
        AdminStudentCreate(
            full_name="Student One",
            email="student@example.com",
            program_type=StudentProgramType.BATCH,
            access_starts_at=datetime(2026, 7, 20),
        )


@pytest.mark.asyncio
async def test_admin_teacher_create_commits_once_after_user_and_teacher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    user = User(
        id=uuid4(),
        full_name="Teacher One",
        email="teacher@example.com",
        role=UserRole.TEACHER,
        is_active=True,
    )
    teacher = Teacher(
        id=uuid4(),
        user_id=user.id,
        display_name="Teacher One",
        is_active=True,
    )
    calls = {}

    async def fake_create_user(self, user_in, *, commit=True):
        calls["user_role"] = user_in.role
        calls["user_commit"] = commit
        return user

    async def fake_create_teacher(self, teacher_in, *, commit=True):
        calls["teacher_user_id"] = teacher_in.user_id
        calls["teacher_commit"] = commit
        return teacher

    monkeypatch.setattr(UserService, "create_user", fake_create_user)
    monkeypatch.setattr(TeacherService, "create_teacher", fake_create_teacher)

    created_user, created_teacher = await AdminService(session).create_teacher(
        AdminTeacherCreate(
            full_name="Teacher One",
            email="teacher@example.com",
            display_name="Teacher One",
        )
    )

    assert created_user is user
    assert created_teacher is teacher
    assert calls == {
        "user_role": UserRole.TEACHER,
        "user_commit": False,
        "teacher_user_id": user.id,
        "teacher_commit": False,
    }
    session.commit.assert_awaited_once()
    assert session.refresh.await_count == 2


@pytest.mark.asyncio
async def test_admin_student_create_commits_once_after_user_and_student(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    user = User(
        id=uuid4(),
        full_name="Student One",
        email="student@example.com",
        role=UserRole.STUDENT,
        is_active=True,
    )
    student = Student(
        id=uuid4(),
        user_id=user.id,
        program_type=StudentProgramType.BATCH,
        status=StudentStatus.ENROLLED,
    )
    calls = {}

    async def fake_create_user(self, user_in, *, commit=True):
        calls["user_role"] = user_in.role
        calls["user_commit"] = commit
        return user

    async def fake_create_student(self, student_in, *, commit=True):
        calls["student_user_id"] = student_in.user_id
        calls["student_program_type"] = student_in.program_type
        calls["student_commit"] = commit
        return student

    monkeypatch.setattr(UserService, "create_user", fake_create_user)
    monkeypatch.setattr(StudentService, "create_student", fake_create_student)

    created_user, created_student = await AdminService(session).create_student(
        AdminStudentCreate(
            full_name="Student One",
            email="student@example.com",
            program_type=StudentProgramType.BATCH,
        )
    )

    assert created_user is user
    assert created_student is student
    assert calls == {
        "user_role": UserRole.STUDENT,
        "user_commit": False,
        "student_user_id": user.id,
        "student_program_type": StudentProgramType.BATCH,
        "student_commit": False,
    }
    session.commit.assert_awaited_once()
    assert session.refresh.await_count == 2
