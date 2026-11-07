from fastapi import APIRouter, Cookie, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import DBSession
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.modules.auth.dependencies import (
    CurrentUser,
)
from app.modules.auth.email import send_password_reset_email
from app.modules.auth.schemas import (
    AuthUserRead,
    LoginRequest,
    PasswordConfirm,
    PasswordRequest,
    SessionRead,
)
from app.modules.auth.service import AuthService
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
from app.modules.users.models import User

router = APIRouter()


def set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key="cp_hub_refresh",
        value=raw_token,
        max_age=settings.auth_refresh_token_days * 86400,
        httponly=True,
        secure=settings.auth_refresh_cookie_secure,
        samesite="lax",
        path="/api/v1/auth",
    )


async def auth_user_read(session: DBSession, user: User) -> AuthUserRead:
    teacher_id = await session.scalar(select(Teacher.id).where(Teacher.user_id == user.id))
    student_id = await session.scalar(select(Student.id).where(Student.user_id == user.id))
    return AuthUserRead(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        teacher_id=teacher_id,
        student_id=student_id,
    )


@router.post("/login", response_model=SessionRead)
async def login(body: LoginRequest, response: Response, session: DBSession) -> SessionRead:
    user = await AuthService(session).authenticate(str(body.email), body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    token, expires_at = AuthService.create_access_token(user)
    refresh_token = await AuthService(session).issue_refresh_token(user)
    set_refresh_cookie(response, refresh_token)
    return SessionRead(
        access_token=token, expires_at=expires_at, user=await auth_user_read(session, user)
    )


@router.post("/refresh", response_model=SessionRead)
async def refresh_session(
    response: Response, session: DBSession, cp_hub_refresh: str | None = Cookie(default=None)
) -> SessionRead:
    if not cp_hub_refresh:
        raise HTTPException(status_code=401, detail="Refresh token required")
    service = AuthService(session)
    user = await service.rotate_refresh_token(cp_hub_refresh)
    if user is None:
        response.delete_cookie("cp_hub_refresh", path="/api/v1/auth")
        raise HTTPException(status_code=401, detail="Refresh token is invalid or expired")
    fresh_refresh_token = await service.issue_refresh_token(user)
    set_refresh_cookie(response, fresh_refresh_token)
    token, expires_at = service.create_access_token(user)
    return SessionRead(
        access_token=token, expires_at=expires_at, user=await auth_user_read(session, user)
    )


@router.post("/logout", status_code=204)
async def logout(
    response: Response, session: DBSession, cp_hub_refresh: str | None = Cookie(default=None)
) -> None:
    if cp_hub_refresh:
        await AuthService(session).revoke_refresh_token(cp_hub_refresh)
    response.delete_cookie("cp_hub_refresh", path="/api/v1/auth")


@router.get("/me", response_model=AuthUserRead)
async def me(user: CurrentUser, session: DBSession) -> AuthUserRead:
    return await auth_user_read(session, user)


@router.post("/password/reset-request", status_code=202)
async def reset_request(body: PasswordRequest, session: DBSession) -> dict[str, str]:
    user = await session.scalar(select(User).where(User.email == str(body.email).lower()))
    if user and user.is_active:
        token = await AuthService(session).issue_password_token(user, "reset")
        await session.commit()
        await send_password_reset_email(user.email, token)
    return {"detail": "If the account exists, a password reset email has been sent."}


@router.post("/password/reset", status_code=204)
async def reset_password(body: PasswordConfirm, session: DBSession) -> None:
    await _set_password(body, session, "reset")


@router.post("/password/setup", status_code=204)
async def setup_password(body: PasswordConfirm, session: DBSession) -> None:
    await _set_password(body, session, "setup")


async def _set_password(body: PasswordConfirm, session: DBSession, purpose: str) -> None:
    try:
        await AuthService(session).set_password(body.token, body.password, purpose)
    except (ValueError, NotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The password link is invalid or has expired",
        ) from exc
