from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.auth.service import AuthService
from app.modules.users.models import User
from app.shared.enums import UserRole


class FakeSession:
    def __init__(self, *, scalar_result=None, user=None) -> None:
        self.scalar = AsyncMock(return_value=scalar_result)
        self.get = AsyncMock(return_value=user)
        self.commit = AsyncMock()


def make_user(*, active: bool = True) -> User:
    return User(
        id=uuid4(),
        full_name="Portal User",
        email="portal@example.com",
        role=UserRole.STUDENT,
        is_active=active,
    )


@pytest.mark.asyncio
async def test_refresh_rotation_claims_the_token_once_and_returns_active_user() -> None:
    user = make_user()
    session = FakeSession(scalar_result=user.id, user=user)

    result = await AuthService(session).rotate_refresh_token("refresh-token")

    assert result is user
    statement = str(session.scalar.await_args.args[0])
    assert "UPDATE refresh_tokens" in statement
    assert "revoked_at IS NULL" in statement


@pytest.mark.asyncio
async def test_refresh_replay_is_rejected_when_atomic_claim_returns_nothing() -> None:
    session = FakeSession(scalar_result=None)

    assert await AuthService(session).rotate_refresh_token("already-used") is None
    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_password_token_claim_is_single_use_and_persists_password() -> None:
    user = make_user()
    session = FakeSession(scalar_result=user.id, user=user)

    result = await AuthService(session).set_password(
        "password-token", "A secure password!", "setup"
    )

    assert result is user
    assert user.password_hash is not None
    assert "UPDATE password_action_tokens" in str(session.scalar.await_args.args[0])
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_inactive_account_cannot_use_password_link() -> None:
    user = make_user(active=False)
    session = FakeSession(scalar_result=user.id, user=user)

    with pytest.raises(ValueError, match="invalid or has expired"):
        await AuthService(session).set_password("password-token", "A secure password!", "reset")

    session.commit.assert_not_awaited()
