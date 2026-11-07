from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.api.deps import DBSession
from app.modules.admin.http.types import DatetimeQuery
from app.modules.admin.schemas import (
    AdminDashboardSummaryRead,
)
from app.modules.read_models.services import (
    AdminDashboardQueryService,
)

router = APIRouter()


def normalize_query_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.get("/dashboard/summary", response_model=AdminDashboardSummaryRead)
async def get_dashboard_summary(
    session: DBSession,
    starts_from: DatetimeQuery = None,
    starts_to: DatetimeQuery = None,
) -> AdminDashboardSummaryRead:
    try:
        return await AdminDashboardQueryService(session).get_dashboard_summary(
            starts_from=normalize_query_datetime(starts_from),
            starts_to=normalize_query_datetime(starts_to),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
