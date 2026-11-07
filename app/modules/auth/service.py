import hashlib
import secrets
from datetime import timedelta

import jwt
from pwdlib import PasswordHash
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.modules.auth.models import PasswordActionToken, RefreshToken
from app.modules.users.models import User
from app.shared.utils import utc_now

password_hash = PasswordHash.recommended()


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def issue_password_token(self, user: User, purpose: str) -> str:
        raw = secrets.token_urlsafe(32)
        await self.session.execute(
            update(PasswordActionToken)
            .where(
                PasswordActionToken.user_id == user.id,
                PasswordActionToken.purpose == purpose,
                PasswordActionToken.used_at.is_(None),
            )
            .values(used_at=utc_now())
        )
        self.session.add(
            PasswordActionToken(
                user_id=user.id,
                token_hash=self.hash_token(raw),
                purpose=purpose,
                expires_at=utc_now() + timedelta(minutes=settings.auth_setup_token_minutes),
            )
        )
        return raw

    async def set_password(self, raw_token: str, password: str, purpose: str) -> User:
        # Claim the token atomically. A read-then-write sequence would let two
        # concurrent password submissions consume the same single-use link.
        user_id = await self.session.scalar(
            update(PasswordActionToken)
            .where(
                PasswordActionToken.token_hash == self.hash_token(raw_token),
                PasswordActionToken.purpose == purpose,
                PasswordActionToken.used_at.is_(None),
                PasswordActionToken.expires_at > utc_now(),
            )
            .values(used_at=utc_now())
            .returning(PasswordActionToken.user_id)
        )
        if user_id is None:
            raise ValueError("The password link is invalid or has expired")
        user = await self.session.get(User, user_id)
        if user is None:
            raise NotFoundError("User not found")
        if not user.is_active:
            raise ValueError("The password link is invalid or has expired")
        user.password_hash = password_hash.hash(password)
        await self.session.commit()
        return user

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self.session.scalar(select(User).where(User.email == email.lower()))
        if user is None or not user.is_active or not user.password_hash:
            return None
        return user if password_hash.verify(password, user.password_hash) else None

    async def issue_refresh_token(self, user: User) -> str:
        raw = secrets.token_urlsafe(48)
        self.session.add(
            RefreshToken(
                user_id=user.id,
                token_hash=self.hash_token(raw),
                expires_at=utc_now() + timedelta(days=settings.auth_refresh_token_days),
            )
        )
        await self.session.commit()
        return raw

    async def rotate_refresh_token(self, raw: str) -> User | None:
        # Atomic compare-and-set closes the refresh-token replay race: exactly
        # one request can revoke and replace an otherwise valid token.
        user_id = await self.session.scalar(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == self.hash_token(raw),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > utc_now(),
            )
            .values(revoked_at=utc_now())
            .returning(RefreshToken.user_id)
        )
        if user_id is None:
            return None
        # Persist the claim before issuing a replacement. This makes a replay
        # impossible even if the request fails after revocation.
        await self.session.commit()
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return user

    async def revoke_refresh_token(self, raw: str) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == self.hash_token(raw),
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=utc_now())
        )
        await self.session.commit()

    @staticmethod
    def create_access_token(user: User) -> tuple[str, object]:
        expires_at = utc_now() + timedelta(minutes=settings.auth_access_token_minutes)
        encoded = jwt.encode(
            {"sub": str(user.id), "role": user.role.value, "exp": expires_at},
            settings.auth_jwt_secret,
            algorithm="HS256",
        )
        return encoded, expires_at
