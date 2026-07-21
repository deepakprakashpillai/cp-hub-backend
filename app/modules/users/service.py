from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_scalars
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate, UserUpdate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_users(self, pagination: PaginationParams) -> Page:
        return await paginate_scalars(
            self.session,
            select(User).order_by(User.created_at.desc()),
            pagination,
        )

    async def get_user(self, user_id: UUID) -> User:
        user = await self.session.get(User, user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    async def create_user(self, user_in: UserCreate, *, commit: bool = True) -> User:
        existing_user = await self.session.scalar(select(User).where(User.email == user_in.email))
        if existing_user is not None:
            raise ConflictError("A user with this email already exists")

        user = User(**user_in.model_dump())
        self.session.add(user)
        if commit:
            await self.session.commit()
            await self.session.refresh(user)
        else:
            await self.session.flush()
        return user

    async def update_user(self, user_id: UUID, user_in: UserUpdate) -> User:
        user = await self.get_user(user_id)
        update_data = user_in.model_dump(exclude_unset=True)

        for non_nullable_field in ("full_name", "email", "is_active"):
            if non_nullable_field in update_data and update_data[non_nullable_field] is None:
                raise BadRequestError(f"{non_nullable_field} cannot be null")

        new_email = update_data.get("email")
        if new_email is not None and new_email != user.email:
            existing_user = await self.session.scalar(select(User).where(User.email == new_email))
            if existing_user is not None and existing_user.id != user.id:
                raise ConflictError("A user with this email already exists")

        for field, value in update_data.items():
            setattr(user, field, value)

        await self.session.commit()
        await self.session.refresh(user)
        return user
