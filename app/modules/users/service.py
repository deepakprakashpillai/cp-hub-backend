from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_scalars
from app.modules.notifications.service import NotificationService
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate, UserUpdate
from app.shared.enums import UserRole


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

    async def set_roles(self, user_id: UUID, roles: list[UserRole], actor_id: UUID) -> User:
        requested = set(roles)
        allowed = {UserRole.ADMIN, UserRole.TEACHER}
        if len(requested) != len(roles) or not requested or not requested <= allowed:
            raise BadRequestError("Roles must be distinct admin and/or teacher roles")
        user = await self.session.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if user is None:
            raise NotFoundError("User not found")
        if user.role not in allowed:
            raise ConflictError("Only admin and teacher accounts can have their roles changed")
        if user.id == actor_id and UserRole.ADMIN not in requested:
            raise ConflictError("An admin cannot remove their own admin access")
        if user.role not in requested:
            user.role = next(iter(requested))
        user.additional_role = next(iter(requested - {user.role}), None)
        await self.session.commit()
        await self.session.refresh(user)
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
        previous_email = user.email
        previous_is_active = user.is_active
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

        service = NotificationService(self.session)
        if "email" in update_data and previous_email != user.email:
            await service.emit_to_users(
                event_type="account.email_changed",
                aggregate_type="user",
                aggregate_id=user.id,
                dedupe_key=f"notification:email-changed:{user.id}:{user.email}",
                recipient_user_ids=[user.id],
                title="Login email changed",
                body="The email address used to sign in to CP Hub was updated.",
                category="account",
                priority="high",
                action_url=None,
                data={
                    "user_id": str(user.id),
                    "previous_email": previous_email,
                    "current_email": user.email,
                },
                include_admins=True,
            )
        if "is_active" in update_data and previous_is_active != user.is_active:
            await service.emit_to_users(
                event_type="account.status_changed",
                aggregate_type="user",
                aggregate_id=user.id,
                dedupe_key=f"notification:account-status:{user.id}:{user.is_active}",
                recipient_user_ids=[user.id],
                title="Account status updated",
                body="Your CP Hub account was enabled."
                if user.is_active
                else "Your CP Hub account was disabled.",
                category="account",
                priority="medium" if user.is_active else "high",
                action_url=None,
                data={
                    "user_id": str(user.id),
                    "previous_status": "active" if previous_is_active else "inactive",
                    "current_status": "active" if user.is_active else "inactive",
                },
                include_admins=True,
            )

        await self.session.commit()
        await self.session.refresh(user)
        return user
