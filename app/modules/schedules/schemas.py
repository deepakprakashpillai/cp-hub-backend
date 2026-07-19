from datetime import datetime

from pydantic import BaseModel

from app.shared.enums import BatchSlot


class TeacherAvailabilitySlotCreate(BaseModel):
    teacher_id: str
    starts_at: datetime
    ends_at: datetime


class BatchScheduleSlotCreate(BaseModel):
    slot: BatchSlot
    starts_at: datetime
    ends_at: datetime
