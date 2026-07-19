from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TeacherBase(BaseModel):
    user_id: UUID
    display_name: str = Field(min_length=1, max_length=150)
    bio: str | None = None
    profile_photo_url: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class TeacherCreate(TeacherBase):
    pass


class TeacherRead(TeacherBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
