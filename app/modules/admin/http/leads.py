from uuid import UUID

from fastapi import APIRouter

from app.api.deps import DBSession
from app.modules.leads.schemas import LeadConversionRead, LeadConvert
from app.modules.leads.workflows import LeadConversionWorkflow

router = APIRouter()


@router.post("/leads/{lead_id}/convert", response_model=LeadConversionRead)
async def convert_lead(
    lead_id: UUID,
    conversion: LeadConvert,
    session: DBSession,
) -> LeadConversionRead:
    return await LeadConversionWorkflow(session).convert_lead(lead_id, conversion)
