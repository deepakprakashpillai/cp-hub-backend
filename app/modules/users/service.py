from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_users(self) -> list[User]:
        result = await self.session.scalars(select(User).order_by(User.created_at.desc()))
        return list(result)

    async def get_user(self, user_id: UUID) -> User:
        user = await self.session.get(User, user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    async def create_user(self, user_in: UserCreate) -> User:
        existing_user = await self.session.scalar(select(User).where(User.email == user_in.email))
        if existing_user is not None:
            raise ConflictError("A user with this email already exists")

        user = User(**user_in.model_dump())
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user
