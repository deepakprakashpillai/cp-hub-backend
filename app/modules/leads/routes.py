from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Query, UploadFile, status

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.leads.schemas import (
    LeadCreate,
    LeadImportPreview,
    LeadImportResult,
    LeadRead,
    LeadSummary,
    LeadUpdate,
)
from app.modules.leads.service import LeadService
from app.shared.enums import LeadStatus

router = APIRouter()
SearchQuery = Annotated[str | None, Query(max_length=150)]
StatusQuery = Annotated[LeadStatus | None, Query(alias="status")]
UploadFileInput = Annotated[UploadFile, File()]


@router.get("", response_model=Page[LeadRead])
async def list_leads(
    session: DBSession,
    pagination: Pagination,
    q: SearchQuery = None,
    status_filter: StatusQuery = None,
) -> Page[LeadRead]:
    return await LeadService(session).list_leads(pagination, q=q, status=status_filter)


@router.post("", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
async def create_lead(lead_in: LeadCreate, session: DBSession) -> LeadRead:
    return await LeadService(session).create_lead(lead_in)


@router.get("/summary", response_model=LeadSummary)
async def get_lead_summary(session: DBSession) -> LeadSummary:
    return await LeadService(session).get_summary()


@router.post("/import/preview", response_model=LeadImportPreview)
async def preview_import_leads(
    session: DBSession,
    file: UploadFileInput,
) -> LeadImportPreview:
    return await LeadService(session).preview_import(file)


@router.post("/import", response_model=LeadImportResult)
async def import_leads(session: DBSession, file: UploadFileInput) -> LeadImportResult:
    return await LeadService(session).import_leads(file)


@router.patch("/{lead_id}", response_model=LeadRead)
async def update_lead(lead_id: UUID, lead_in: LeadUpdate, session: DBSession) -> LeadRead:
    return await LeadService(session).update_lead(lead_id, lead_in)


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(lead_id: UUID, session: DBSession) -> None:
    await LeadService(session).delete_lead(lead_id)
