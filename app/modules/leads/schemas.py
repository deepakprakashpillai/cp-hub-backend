from pydantic import BaseModel, EmailStr

from app.shared.enums import LeadStatus


class LeadCreate(BaseModel):
    full_name: str
    email: EmailStr | None = None
    phone: str | None = None
    status: LeadStatus = LeadStatus.NEW


class LeadRead(LeadCreate):
    id: str
