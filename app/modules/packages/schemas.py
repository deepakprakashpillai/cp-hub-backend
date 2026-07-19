from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PackageBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    duration_days: int = Field(gt=0)
    price_amount: int = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    is_active: bool = True


class PackageCreate(PackageBase):
    pass


class PackageUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    duration_days: int | None = Field(default=None, gt=0)
    price_amount: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    is_active: bool | None = None


class PackageRead(PackageBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
