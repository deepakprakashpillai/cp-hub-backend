from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.modules.leads.schemas import LeadConversionRead, LeadConvert
from app.modules.leads.service import LeadService
from app.modules.students.schemas import StudentCreate
from app.modules.students.service import StudentService
from app.modules.users.schemas import UserCreate
from app.modules.users.service import UserService
from app.shared.enums import LeadStatus, StudentStatus, UserRole
from app.shared.utils import utc_now


class LeadConversionWorkflow:
    """Atomically converts an enrolled lead into user and student records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def convert_lead(
        self,
        lead_id: UUID,
        conversion: LeadConvert,
    ) -> LeadConversionRead:
        lead_service = LeadService(self.session)
        lead = await lead_service.get_lead(lead_id)
        if lead.status != LeadStatus.ENROLLED:
            raise ConflictError("Only enrolled leads can be converted")
        if lead.converted_student_id is not None:
            raise ConflictError("Lead has already been converted")

        email = str(conversion.email).strip().lower()
        await lead_service._ensure_not_duplicate(email, lead.phone, exclude_id=lead.id)
        user = await UserService(self.session).create_user(
            UserCreate(
                full_name=lead.full_name,
                email=email,
                phone=lead.phone,
                role=UserRole.STUDENT,
            ),
            commit=False,
        )
        student = await StudentService(self.session).create_student(
            StudentCreate(
                user_id=user.id,
                program_type=conversion.program_type,
                status=StudentStatus.ENROLLED,
            ),
            commit=False,
        )
        lead.email = email
        lead.converted_student_id = student.id
        lead.converted_at = utc_now()
        await self.session.commit()
        await self.session.refresh(lead)
        return LeadConversionRead(lead=lead, student_id=student.id)
