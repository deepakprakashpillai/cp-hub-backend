from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.modules.students.schemas import StudentRead, normalize_utc_datetime
from app.modules.teachers.schemas import TeacherRead
from app.modules.users.schemas import UserRead
from app.shared.enums import StudentProgramType, StudentStatus


class AdminUserCreateFields(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    is_active: bool = True


class AdminTeacherCreate(AdminUserCreateFields):
    display_name: str = Field(min_length=1, max_length=150)
    bio: str | None = None
    profile_photo_url: str | None = Field(default=None, max_length=500)


class AdminStudentCreate(AdminUserCreateFields):
    program_type: StudentProgramType
    status: StudentStatus = StudentStatus.ENROLLED
    access_starts_at: datetime | None = None
    access_ends_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_access_window(self) -> "AdminStudentCreate":
        if self.access_starts_at is not None:
            self.access_starts_at = normalize_utc_datetime(self.access_starts_at)
        if self.access_ends_at is not None:
            self.access_ends_at = normalize_utc_datetime(self.access_ends_at)
        if (
            self.access_starts_at is not None
            and self.access_ends_at is not None
            and self.access_starts_at >= self.access_ends_at
        ):
            raise ValueError("access_starts_at must be before access_ends_at")
        return self


class AdminTeacherRead(BaseModel):
    user: UserRead
    teacher: TeacherRead


class AdminStudentRead(BaseModel):
    user: UserRead
    student: StudentRead
