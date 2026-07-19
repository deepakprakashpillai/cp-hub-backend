from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.enums import PaymentMethod
from app.shared.utils import utc_now


def normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone info")
    return value.astimezone(UTC)


class StudentPaymentCreate(BaseModel):
    student_id: UUID
    package_id: UUID | None = None
    amount_paid: int = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    payment_method: PaymentMethod
    paid_at: datetime = Field(default_factory=utc_now)
    created_by_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_paid_at(self) -> "StudentPaymentCreate":
        self.paid_at = normalize_utc_datetime(self.paid_at)
        return self


class StudentPaymentUpdate(BaseModel):
    student_id: UUID | None = None
    package_id: UUID | None = None
    amount_paid: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    payment_method: PaymentMethod | None = None
    paid_at: datetime | None = None
    created_by_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_paid_at(self) -> "StudentPaymentUpdate":
        if self.paid_at is not None:
            self.paid_at = normalize_utc_datetime(self.paid_at)
        return self


class StudentPaymentRead(StudentPaymentCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
