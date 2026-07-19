from datetime import datetime

from pydantic import BaseModel

from app.shared.enums import ClassSessionStatus, StudentProgramType


class ClassSessionCreate(BaseModel):
    program_type: StudentProgramType
    starts_at: datetime
    ends_at: datetime
    status: ClassSessionStatus = ClassSessionStatus.SCHEDULED


class ClassSessionRead(ClassSessionCreate):
    id: str
