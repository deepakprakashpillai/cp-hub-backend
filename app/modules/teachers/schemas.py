from pydantic import BaseModel


class TeacherCreate(BaseModel):
    user_id: str
    display_name: str


class TeacherRead(TeacherCreate):
    id: str
