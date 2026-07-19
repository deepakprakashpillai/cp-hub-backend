from pydantic import BaseModel

from app.shared.enums import StudentProgramType


class StudentCreate(BaseModel):
    user_id: str
    program_type: StudentProgramType


class StudentRead(StudentCreate):
    id: str
