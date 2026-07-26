from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.shared.enums import LeadStatus, StudentProgramType


class LeadBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    source: str | None = Field(default=None, max_length=100)
    status: LeadStatus = LeadStatus.NEW


class LeadCreate(LeadBase):
    pass


class LeadUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    source: str | None = Field(default=None, max_length=100)
    status: LeadStatus | None = None


class LeadRead(LeadBase):
    id: UUID
    converted_student_id: UUID | None
    converted_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadSummary(BaseModel):
    total: int
    new: int
    contacted: int
    trial_booked: int
    enrolled: int
    lost: int


class LeadConvert(BaseModel):
    email: EmailStr
    program_type: StudentProgramType


class LeadConversionRead(BaseModel):
    lead: LeadRead
    student_id: UUID


class LeadImportIssue(BaseModel):
    row: int
    message: str


class LeadImportPreview(BaseModel):
    total_rows: int
    valid_rows: int
    duplicate_rows: int
    invalid_rows: int
    issues: list[LeadImportIssue]


class LeadImportResult(BaseModel):
    created_rows: int
    skipped_duplicate_rows: int
    skipped_invalid_rows: int
