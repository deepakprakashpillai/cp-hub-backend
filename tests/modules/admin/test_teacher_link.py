from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db_session
from app.core.exceptions import ConflictError, NotFoundError
from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.read_models.account_services import AdminAccountWorkflow
from app.modules.read_models.admin_schemas import AdminTeacherLinkRequest
from app.modules.teachers.models import Teacher
from app.modules.users.models import User
from app.shared.enums import UserRole


def account(role=UserRole.ADMIN):
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        full_name="Admin",
        email="Name@example.com",
        role=role,
        is_active=True,
        password_hash="unchanged",
        created_at=now,
        updated_at=now,
    )


def profile(user):
    now = datetime.now(UTC)
    return Teacher(
        id=uuid4(),
        user_id=user.id,
        display_name="Original",
        bio="Keep this",
        is_active=False,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_link_reuses_profile_and_restores_role_without_overwriting():
    user = account()
    teacher = profile(user)
    session = AsyncMock()
    session.scalar.side_effect = [user, teacher]
    result = await AdminAccountWorkflow(session).link_existing_admin(
        AdminTeacherLinkRequest(user_id=user.id, display_name="Ignored", bio="Ignored")
    )
    assert result.profile_already_existed is True
    assert result.teacher.display_name == "Original"
    assert result.teacher.bio == "Keep this"
    assert result.teacher.is_active is False
    assert result.user.roles == [UserRole.ADMIN, UserRole.TEACHER]
    assert user.password_hash == "unchanged"
    assert "FOR UPDATE" in str(session.scalar.await_args_list[0].args[0])
    session.add.assert_not_called()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_failure_rolls_back_role_change():
    user = account()
    session = AsyncMock()
    session.add = Mock()
    session.scalar.side_effect = [user, None]
    session.flush.side_effect = RuntimeError("insert failed")
    with pytest.raises(RuntimeError, match="insert failed"):
        await AdminAccountWorkflow(session).link_existing_admin(
            AdminTeacherLinkRequest(user_id=user.id, display_name="Teacher")
        )
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target", [None, UserRole.STUDENT, UserRole.TEACHER, UserRole.LEAD_MANAGER]
)
async def test_link_rejects_unsupported_target(target):
    session = AsyncMock()
    session.scalar.return_value = account(target) if target else None
    with pytest.raises(NotFoundError if target is None else ConflictError):
        await AdminAccountWorkflow(session).link_existing_admin(
            AdminTeacherLinkRequest(user_id=uuid4(), display_name="Teacher")
        )
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


def test_lookup_and_link_require_admin_and_lookup_is_exact():
    user = account()
    session = AsyncMock()
    row = Mock()
    row.one_or_none.return_value = (user, None)
    session.execute.return_value = row
    app.dependency_overrides[get_db_session] = lambda: session
    try:
        with TestClient(app) as client:
            assert (
                client.get("/api/v1/admin/users/lookup", params={"email": user.email}).status_code
                == 401
            )
            app.dependency_overrides[get_current_user] = lambda: account(UserRole.TEACHER)
            assert (
                client.get("/api/v1/admin/users/lookup", params={"email": user.email}).status_code
                == 403
            )
            assert (
                client.post(
                    "/api/v1/admin/teachers/link-existing",
                    json={"user_id": str(user.id), "display_name": "A"},
                ).status_code
                == 403
            )
            app.dependency_overrides[get_current_user] = lambda: user
            response = client.get(
                "/api/v1/admin/users/lookup", params={"email": "Name@EXAMPLE.COM"}
            )
            assert response.status_code == 200
            assert response.json()["user"]["id"] == str(user.id)
            assert response.json()["teacher_id"] is None
            statement = session.execute.await_args.args[0]
            assert "users.email =" in str(statement)
            assert "ILIKE" not in str(statement)
            assert statement.compile().params["email_1"] == "Name@example.com"
            row.one_or_none.return_value = None
            assert (
                client.get(
                    "/api/v1/admin/users/lookup", params={"email": "nobody@example.com"}
                ).status_code
                == 404
            )
            assert (
                client.get(
                    "/api/v1/admin/users/lookup", params={"email": "not-an-email"}
                ).status_code
                == 422
            )
    finally:
        app.dependency_overrides.clear()


def test_admin_can_link_own_account_and_retry_existing_profile():
    user = account()
    teacher = profile(user)
    session = AsyncMock()
    session.scalar.side_effect = [user, teacher]
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/teachers/link-existing",
                json={"user_id": str(user.id), "display_name": "New name"},
            )
            assert response.status_code == 200
            result = response.json()
            assert result["user"]["id"] == str(user.id)
            assert result["user"]["roles"] == ["admin", "teacher"]
            assert result["teacher"]["id"] == str(teacher.id)
            assert result["teacher"]["display_name"] == "Original"
            assert result["profile_already_existed"] is True
    finally:
        app.dependency_overrides.clear()
