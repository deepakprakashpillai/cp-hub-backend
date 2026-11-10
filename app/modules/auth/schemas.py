from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.shared.enums import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class PasswordRequest(BaseModel):
    email: EmailStr


class PasswordConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=12, max_length=128)


class AuthUserRead(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr
    role: UserRole
    roles: list[UserRole]
    teacher_id: UUID | None = None
    student_id: UUID | None = None


class SessionRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: AuthUserRead
