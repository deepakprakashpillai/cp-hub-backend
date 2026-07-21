from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError
from app.modules.users.models import User
from app.modules.users.schemas import UserUpdate
from app.modules.users.service import UserService
from app.shared.enums import UserRole


class FakeSession:
    def __init__(self, user: User, existing_user: User | None = None) -> None:
        self.user = user
        self.get = AsyncMock(return_value=user)
        self.scalar = AsyncMock(return_value=existing_user)
        self.commit = AsyncMock()
        self.refresh = AsyncMock()


def timestamp() -> datetime:
    return datetime(2026, 7, 22, tzinfo=UTC)


def user(email: str = "user@example.com") -> User:
    return User(
        id=uuid4(),
        full_name="User One",
        email=email,
        role=UserRole.STUDENT,
        is_active=True,
        created_at=timestamp(),
        updated_at=timestamp(),
    )


@pytest.mark.asyncio
async def test_user_update_changes_account_fields() -> None:
    existing_user = user()
    session = FakeSession(existing_user)

    updated = await UserService(session).update_user(
        existing_user.id,
        UserUpdate(
            full_name="Updated User",
            email="updated@example.com",
            phone="12345",
            is_active=False,
        ),
    )

    assert updated.full_name == "Updated User"
    assert updated.email == "updated@example.com"
    assert updated.phone == "12345"
    assert updated.is_active is False
    session.scalar.assert_awaited_once()
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(existing_user)


@pytest.mark.asyncio
async def test_user_update_rejects_duplicate_email() -> None:
    existing_user = user()
    duplicate_user = user("duplicate@example.com")
    session = FakeSession(existing_user, existing_user=duplicate_user)

    with pytest.raises(ConflictError) as exc_info:
        await UserService(session).update_user(
            existing_user.id,
            UserUpdate(email="duplicate@example.com"),
        )

    assert exc_info.value.detail == "A user with this email already exists"
    session.commit.assert_not_awaited()
