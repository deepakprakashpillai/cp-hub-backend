from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.routes import auth_user_read, reset_password
from app.modules.auth.schemas import PasswordConfirm
from app.modules.auth.service import AuthService
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
from app.modules.users.models import User
from app.shared.enums import StudentProgramType, UserRole
from app.shared.utils import utc_now


class FakeSession:
    def __init__(self, user: User) -> None:
        self.get = AsyncMock(return_value=user)
        self.scalar = AsyncMock(side_effect=[uuid4(), uuid4()])


def make_user() -> User:
    return User(
        id=uuid4(),
        full_name="Student",
        email="student@example.com",
        role=UserRole.STUDENT,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_current_user_rejects_malformed_bearer_header() -> None:
    with pytest.raises(HTTPException, match="Authentication required"):
        await get_current_user(AsyncMock(), "Token abc")


@pytest.mark.asyncio
async def test_current_user_accepts_valid_bearer_token_for_active_account() -> None:
    user = make_user()
    token = jwt.encode(
        {"sub": str(user.id), "exp": utc_now().timestamp() + 60},
        settings.auth_jwt_secret,
        algorithm="HS256",
    )
    session = FakeSession(user)

    assert await get_current_user(session, f"Bearer {token}") is user


@pytest.mark.asyncio
async def test_session_identity_contains_teacher_and_student_profile_ids() -> None:
    user = make_user()
    session = FakeSession(user)

    identity = await auth_user_read(session, user)

    assert identity.teacher_id is not None
    assert identity.student_id is not None


def test_student_model_can_be_constructed_for_portal_identity() -> None:
    student = Student(id=uuid4(), user_id=uuid4(), program_type=StudentProgramType.BATCH)
    teacher = Teacher(id=uuid4(), user_id=uuid4(), display_name="Teacher")

    assert student.user_id is not None
    assert teacher.user_id is not None


@pytest.mark.asyncio
async def test_invalid_password_link_returns_bad_request(monkeypatch: pytest.MonkeyPatch) -> None:
    async def reject_token(self: AuthService, raw_token: str, password: str, purpose: str) -> User:
        raise ValueError("The password link is invalid or has expired")

    monkeypatch.setattr(AuthService, "set_password", reject_token)
    body = PasswordConfirm(token="x" * 32, password="a secure password")

    with pytest.raises(HTTPException) as exc_info:
        await reset_password(body, AsyncMock())

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "The password link is invalid or has expired"
