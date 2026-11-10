from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.modules.batch_groups.schemas import BatchGroupRead
from app.modules.bookings.schemas import (
    AdminBatchClassReschedule as AdminBatchClassReschedule,
)
from app.modules.bookings.schemas import BookingRead
from app.modules.packages.schemas import PackageSummary
from app.modules.read_models.schemas import (
    AdminActivityActorSummary as AdminActivityActorSummary,
)
from app.modules.read_models.schemas import (
    AdminActivityStudentSummary as AdminActivityStudentSummary,
)
from app.modules.read_models.schemas import (
    AdminClassActivityRead as AdminClassActivityRead,
)
from app.modules.read_models.schemas import (
    AdminClassBatchGroupSummary as AdminClassBatchGroupSummary,
)
from app.modules.read_models.schemas import (
    AdminClassBookingCounts as AdminClassBookingCounts,
)
from app.modules.read_models.schemas import (
    AdminClassRead,
)
from app.modules.read_models.schemas import (
    AdminClassRosterBookingRead as AdminClassRosterBookingRead,
)
from app.modules.read_models.schemas import (
    AdminClassStudentSummary as AdminClassStudentSummary,
)
from app.modules.read_models.schemas import (
    AdminClassTeacherSummary as AdminClassTeacherSummary,
)
from app.modules.read_models.schemas import AdminStudentRead as AdminStudentRead
from app.modules.read_models.schemas import AdminTeacherRead as AdminTeacherRead
from app.modules.student_access_grants.schemas import StudentAccessGrantRead
from app.modules.student_payments.schemas import (
    StudentPaymentRead,
)
from app.modules.student_payments.schemas import (
    normalize_utc_datetime as normalize_paid_at,
)
from app.modules.students.schemas import StudentUpdate, normalize_utc_datetime
from app.modules.teachers.schemas import TeacherRead
from app.modules.users.schemas import UserRead
from app.shared.enums import (
    PaymentMethod,
    StudentAccessGrantType,
    StudentProgramType,
    StudentStatus,
)
from app.shared.enums import (
    SortOrder as SortOrder,
)
from app.shared.utils import utc_now


class AdminStudentAccessState(StrEnum):
    VALID = "valid"
    EXPIRED = "expired"
    NOT_STARTED = "not_started"
    NONE = "none"


class AdminStudentSortBy(StrEnum):
    CREATED_AT = "created_at"
    JOINED_AT = "joined_at"
    NAME = "name"
    STATUS = "status"
    PROGRAM_TYPE = "program_type"
    ACCESS_ENDS_AT = "access_ends_at"


class AdminTeacherSortBy(StrEnum):
    CREATED_AT = "created_at"
    NAME = "name"
    DISPLAY_NAME = "display_name"
    IS_ACTIVE = "is_active"


class AdminBatchGroupSortBy(StrEnum):
    CREATED_AT = "created_at"
    NAME = "name"
    ACTIVE_MEMBER_COUNT = "active_member_count"
    UPCOMING_SCHEDULED_COUNT = "upcoming_scheduled_count"
    IS_ACTIVE = "is_active"


class AdminPackageSortBy(StrEnum):
    CREATED_AT = "created_at"
    NAME = "name"
    DURATION_DAYS = "duration_days"
    PRICE_AMOUNT = "price_amount"
    IS_ACTIVE = "is_active"


class AdminPaymentSortBy(StrEnum):
    PAID_AT = "paid_at"
    AMOUNT_PAID = "amount_paid"


class AdminUserCreateFields(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    is_active: bool = True


class AdminTeacherCreate(AdminUserCreateFields):
    display_name: str = Field(min_length=1, max_length=150)
    bio: str | None = None
    profile_photo_url: str | None = Field(default=None, max_length=500)


class AdminTeacherLinkRequest(BaseModel):
    user_id: UUID
    display_name: str = Field(min_length=1, max_length=150)
    bio: str | None = None
    profile_photo_url: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class AdminTeacherLinkRead(BaseModel):
    user: UserRead
    teacher: TeacherRead
    profile_already_existed: bool


class AdminUserLookupRead(BaseModel):
    user: UserRead
    teacher_id: UUID | None


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


class AdminStudentPaymentUpdate(BaseModel):
    package_id: UUID | None = None
    amount_paid: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    payment_method: PaymentMethod | None = None
    paid_at: datetime | None = None
    created_by_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_paid_at(self) -> "AdminStudentPaymentUpdate":
        if self.paid_at is not None:
            self.paid_at = normalize_paid_at(self.paid_at)
        return self


class AdminPaymentCreate(AdminStudentPaymentCreate):
    student_id: UUID


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
    allow_package_access_override: bool = False

    @model_validator(mode="after")
    def validate_override_reason(self) -> "AdminStudentBatchGroupSet":
        if self.allow_package_access_override and not (self.reason or "").strip():
            raise ValueError("reason is required for package access override")
        return self


class AdminStudentUpdate(StudentUpdate):
    assigned_teacher_id: UUID | None = None


class AdminBatchGroupRead(BatchGroupRead):
    active_member_count: int
    upcoming_scheduled_count: int


class AdminClassRescheduleResult(BaseModel):
    class_session: AdminClassRead
    booking: BookingRead


class AdminBatchClassRescheduleResult(BaseModel):
    class_session: AdminClassRead
    bookings: list[BookingRead]


class AdminDashboardWindowRead(BaseModel):
    starts_from: datetime
    starts_to: datetime
    generated_at: datetime


class AdminDashboardStudentSummary(BaseModel):
    total: int
    active: int
    enrolled: int
    paused: int
    completed: int
    cancelled: int
    active_with_valid_access: int
    expired_access: int


class AdminDashboardTeacherSummary(BaseModel):
    total: int
    active: int
    inactive: int


class AdminDashboardBatchGroupSummary(BaseModel):
    total: int
    active: int
    inactive: int


class AdminDashboardClassSummary(BaseModel):
    scheduled: int
    completed: int
    cancelled: int


class AdminDashboardBookingSummary(BaseModel):
    booked: int
    cancelled: int
    attended: int
    missed: int


class AdminDashboardPaymentSummary(BaseModel):
    count: int
    total_amount_paid: int


class AdminDashboardActionItems(BaseModel):
    no_access: int
    expired_access: int
    unconverted_enrolled_leads: int
    attendance_due: int


class AdminTeacherAvailabilityGenerationResult(BaseModel):
    rules_checked: int
    slots_created: int
    slots_cancelled: int
    slots_skipped: int


class AdminDashboardSummaryRead(BaseModel):
    window: AdminDashboardWindowRead
    students: AdminDashboardStudentSummary
    teachers: AdminDashboardTeacherSummary
    batch_groups: AdminDashboardBatchGroupSummary
    classes: AdminDashboardClassSummary
    bookings: AdminDashboardBookingSummary
    payments: AdminDashboardPaymentSummary
    action_items: AdminDashboardActionItems


class AdminStudentPaymentRead(StudentPaymentRead):
    pass


class AdminPaymentStudentSummary(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None


class AdminPaymentRead(StudentPaymentRead):
    student: AdminPaymentStudentSummary
    package: PackageSummary | None = None


class AdminPaymentMethodSummary(BaseModel):
    payment_method: PaymentMethod
    count: int
    total_amount_paid: int


class AdminPaymentCurrencySummary(BaseModel):
    currency: str
    count: int
    total_amount_paid: int
    average_amount_paid: int
    methods: list[AdminPaymentMethodSummary]


class AdminPaymentSummaryRead(BaseModel):
    currencies: list[AdminPaymentCurrencySummary]


class AdminStudentAccessGrantRead(StudentAccessGrantRead):
    pass
