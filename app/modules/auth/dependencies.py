from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select

from app.api.deps import DBSession
from app.core.config import settings
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
from app.modules.users.models import User
from app.shared.enums import UserRole


async def get_current_user(
    session: DBSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
        user_id = UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account is inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    async def guard(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return guard


async def get_current_teacher(user: CurrentUser, session: DBSession) -> Teacher:
    if user.role != UserRole.TEACHER:
        raise HTTPException(status_code=403, detail="Teacher role required")
    teacher = await session.scalar(select(Teacher).where(Teacher.user_id == user.id))
    if teacher is None or not teacher.is_active:
        raise HTTPException(status_code=403, detail="Teacher profile is inactive")
    return teacher


async def get_current_student(user: CurrentUser, session: DBSession) -> Student:
    if user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Student role required")
    student = await session.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise HTTPException(status_code=403, detail="Student profile is unavailable")
    return student
