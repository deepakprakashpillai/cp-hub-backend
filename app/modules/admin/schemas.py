from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.modules.student_access_grants.schemas import StudentAccessGrantRead
from app.modules.student_payments.schemas import (
    StudentPaymentRead,
)
from app.modules.student_payments.schemas import (
    normalize_utc_datetime as normalize_paid_at,
)
from app.modules.students.schemas import StudentRead, normalize_utc_datetime
from app.modules.teachers.schemas import TeacherRead
from app.modules.users.schemas import UserRead
from app.shared.enums import (
    PaymentMethod,
    StudentAccessGrantType,
    StudentProgramType,
    StudentStatus,
)
from app.shared.utils import utc_now


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


class AdminStudentPaymentCreate(BaseModel):
    package_id: UUID | None = None
    amount_paid: int = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    payment_method: PaymentMethod
    paid_at: datetime = Field(default_factory=utc_now)
    created_by_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_paid_at(self) -> "AdminStudentPaymentCreate":
        self.paid_at = normalize_paid_at(self.paid_at)
        return self


class AdminStudentAccessGrantCreate(BaseModel):
    package_id: UUID | None = None
    grant_type: StudentAccessGrantType
    duration_days: int | None = Field(default=None, gt=0)
    access_starts_at: datetime | None = None
    extend_current_access: bool = True
    created_by_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_access_starts_at(self) -> "AdminStudentAccessGrantCreate":
        if self.access_starts_at is not None:
            self.access_starts_at = normalize_utc_datetime(self.access_starts_at)
        return self


class AdminStudentBatchGroupSet(BaseModel):
    batch_group_id: UUID
    assigned_by_user_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=1000)


class AdminTeacherRead(BaseModel):
    user: UserRead
    teacher: TeacherRead


class AdminStudentRead(BaseModel):
    user: UserRead
    student: StudentRead


class AdminStudentPaymentRead(StudentPaymentRead):
    pass


class AdminStudentAccessGrantRead(StudentAccessGrantRead):
    pass
