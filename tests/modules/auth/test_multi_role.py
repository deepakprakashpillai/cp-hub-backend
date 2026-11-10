from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response

from app.core.exceptions import BadRequestError, ConflictError
from app.modules.auth.dependencies import get_current_teacher, require_roles
from app.modules.auth.routes import auth_user_read, login, me, refresh_session
from app.modules.auth.schemas import LoginRequest
from app.modules.auth.service import AuthService
from app.modules.teachers.models import Teacher
from app.modules.teachers.schemas import TeacherCreate
from app.modules.teachers.service import TeacherService
from app.modules.users.models import User
from app.modules.users.service import UserService
from app.shared.enums import UserRole


def account(role=UserRole.ADMIN, additional_role=None):
    return User(
        id=uuid4(),
        full_name="Person",
        email="person@example.com",
        role=role,
        additional_role=additional_role,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_roles_control_both_guards_and_live_changes():
    user = account()
    admin_guard = require_roles(UserRole.ADMIN)
    teacher = Teacher(id=uuid4(), user_id=user.id, display_name="Person", is_active=True)
    session = AsyncMock()
    session.scalar.return_value = teacher
    await admin_guard(user)
    with pytest.raises(HTTPException) as exc:
        await get_current_teacher(user, session)
    assert exc.value.status_code == 403
    user.additional_role = UserRole.TEACHER
    assert await get_current_teacher(user, session) is teacher
    user.role, user.additional_role = UserRole.TEACHER, None
    with pytest.raises(HTTPException) as exc:
        await admin_guard(user)
    assert exc.value.status_code == 403
    assert await get_current_teacher(user, session) is teacher
    assert "teachers.user_id" in str(session.scalar.await_args.args[0])


@pytest.mark.asyncio
async def test_identity_contains_roles_and_existing_profile():
    user = account(UserRole.TEACHER, UserRole.ADMIN)
    teacher_id = uuid4()
    session = AsyncMock()
    session.scalar.side_effect = [teacher_id, None]
    identity = await auth_user_read(session, user)
    assert identity.role == UserRole.TEACHER
    assert identity.roles == [UserRole.TEACHER, UserRole.ADMIN]
    assert identity.teacher_id == teacher_id
    assert AuthService.create_access_token(user)[0]


@pytest.mark.asyncio
async def test_login_refresh_and_me_return_same_roles_and_profile(monkeypatch):
    user = account(UserRole.ADMIN, UserRole.TEACHER)
    teacher_id = uuid4()
    session = AsyncMock()
    session.scalar.side_effect = [teacher_id, None] * 3
    monkeypatch.setattr(AuthService, "authenticate", AsyncMock(return_value=user))
    monkeypatch.setattr(AuthService, "issue_refresh_token", AsyncMock(return_value="refresh"))
    monkeypatch.setattr(AuthService, "rotate_refresh_token", AsyncMock(return_value=user))
    logged_in = await login(
        LoginRequest(email=user.email, password="password"), Response(), session
    )
    refreshed = await refresh_session(Response(), session, "refresh")
    identity = await me(user, session)
    for result in (logged_in.user, refreshed.user, identity):
        assert result.roles == [UserRole.ADMIN, UserRole.TEACHER]
        assert result.role == UserRole.ADMIN
        assert result.teacher_id == teacher_id


@pytest.mark.asyncio
async def test_admin_can_grant_and_remove_complementary_role_without_changing_identity():
    user = account(UserRole.TEACHER)
    session = AsyncMock()
    session.scalar.return_value = user
    actor_id = uuid4()
    await UserService(session).set_roles(user.id, [UserRole.ADMIN, UserRole.TEACHER], actor_id)
    assert user.roles == [UserRole.TEACHER, UserRole.ADMIN]
    await UserService(session).set_roles(user.id, [UserRole.ADMIN], actor_id)
    assert user.roles == [UserRole.ADMIN]
    assert "FOR UPDATE" in str(session.scalar.await_args.args[0])


@pytest.mark.asyncio
async def test_role_updates_reject_invalid_or_self_admin_removal():
    user = account()
    session = AsyncMock()
    session.scalar.return_value = user
    service = UserService(session)
    with pytest.raises(ConflictError):
        await service.set_roles(user.id, [UserRole.TEACHER], user.id)
    with pytest.raises(BadRequestError):
        await service.set_roles(user.id, [UserRole.ADMIN, UserRole.ADMIN], uuid4())
    user.role = UserRole.STUDENT
    with pytest.raises(ConflictError):
        await service.set_roles(user.id, [UserRole.ADMIN], uuid4())
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_teacher_profile_can_link_to_existing_admin_teacher():
    user = account(additional_role=UserRole.TEACHER)
    session = AsyncMock()
    session.scalar.side_effect = [user, None, user, Teacher(user_id=user.id)]
    session.add = Mock()
    teacher = await TeacherService(session).create_teacher(
        TeacherCreate(user_id=user.id, display_name="Person")
    )
    assert teacher.user_id == user.id
    session.add.assert_called_once_with(teacher)
    with pytest.raises(ConflictError):
        await TeacherService(session).create_teacher(
            TeacherCreate(user_id=user.id, display_name="Person")
        )
