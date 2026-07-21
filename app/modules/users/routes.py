from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.users.schemas import UserCreate, UserRead
from app.modules.users.service import UserService

router = APIRouter()


@router.get("", response_model=Page[UserRead])
async def list_users(session: DBSession, pagination: Pagination) -> Page[UserRead]:
    return await UserService(session).list_users(pagination)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    session: DBSession,
) -> UserRead:
    return await UserService(session).create_user(user_in)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: UUID,
    session: DBSession,
) -> UserRead:
    return await UserService(session).get_user(user_id)
