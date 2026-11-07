from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.modules.bookings.schemas import BookingRead
from app.modules.classes.schemas import ClassSessionRead
from app.modules.students.schemas import StudentRead
from app.modules.teachers.schemas import TeacherRead
from app.modules.users.schemas import UserRead
from app.shared.enums import BookingEventType, StudentStatus, UserRole


class AdminTeacherRead(BaseModel):
    user: UserRead
    teacher: TeacherRead


class AdminStudentRead(BaseModel):
    user: UserRead
    student: StudentRead
    assigned_teacher: AdminTeacherRead | None = None


class AdminClassTeacherSummary(BaseModel):
    id: UUID
    display_name: str
    full_name: str
    profile_photo_url: str | None


class AdminClassBatchGroupSummary(BaseModel):
    id: UUID
    name: str
    is_active: bool


class AdminClassStudentSummary(BaseModel):
    id: UUID
    user_id: UUID
    full_name: str
    email: EmailStr
    phone: str | None
    status: StudentStatus


class AdminClassBookingCounts(BaseModel):
    booked: int = 0
    cancelled: int = 0
    attended: int = 0
    missed: int = 0


class AdminClassRead(ClassSessionRead):
    teacher: AdminClassTeacherSummary | None = None
    batch_group: AdminClassBatchGroupSummary | None = None
    primary_student: AdminClassStudentSummary | None = None
    booking_counts: AdminClassBookingCounts


class AdminClassRosterBookingRead(BookingRead):
    student: AdminClassStudentSummary


class AdminActivityStudentSummary(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr


class AdminActivityActorSummary(BaseModel):
    id: UUID
    full_name: str
    role: UserRole


class AdminClassActivityRead(BaseModel):
    id: UUID
    class_session_id: UUID
    booking_id: UUID | None
    student: AdminActivityStudentSummary | None
    event_type: BookingEventType
    reason: str
    metadata: dict
    actor: AdminActivityActorSummary | None
    actor_label: str
    created_at: datetime
