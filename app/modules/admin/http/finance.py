from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.admin.http.types import (
    CurrencyQuery,
    DatetimeQuery,
    PaymentMethodQuery,
    PaymentSortByQuery,
    SearchQuery,
    SortOrderQuery,
)
from app.modules.admin.schemas import (
    AdminPaymentCreate,
    AdminPaymentRead,
    AdminPaymentSortBy,
    AdminPaymentSummaryRead,
    AdminStudentPaymentUpdate,
    SortOrder,
)
from app.modules.read_models.services import (
    AdminFinanceService,
)

router = APIRouter()


def normalize_query_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.get("/payments/summary", response_model=AdminPaymentSummaryRead)
async def get_payment_summary(
    session: DBSession,
    q: SearchQuery = None,
    payment_method: PaymentMethodQuery = None,
    package_id: UUID | None = None,
    currency: CurrencyQuery = None,
    paid_from: DatetimeQuery = None,
    paid_to: DatetimeQuery = None,
) -> AdminPaymentSummaryRead:
    try:
        return await AdminFinanceService(session).get_payment_summary(
            q=q,
            payment_method=payment_method,
            package_id=package_id,
            currency=currency,
            paid_from=normalize_query_datetime(paid_from),
            paid_to=normalize_query_datetime(paid_to),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/payments", response_model=Page[AdminPaymentRead])
async def list_payments(
    session: DBSession,
    pagination: Pagination,
    q: SearchQuery = None,
    payment_method: PaymentMethodQuery = None,
    package_id: UUID | None = None,
    currency: CurrencyQuery = None,
    paid_from: DatetimeQuery = None,
    paid_to: DatetimeQuery = None,
    sort_by: PaymentSortByQuery = AdminPaymentSortBy.PAID_AT,
    sort_order: SortOrderQuery = SortOrder.DESC,
) -> Page[AdminPaymentRead]:
    try:
        return await AdminFinanceService(session).list_payments(
            pagination,
            q=q,
            payment_method=payment_method,
            package_id=package_id,
            currency=currency,
            paid_from=normalize_query_datetime(paid_from),
            paid_to=normalize_query_datetime(paid_to),
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/payments", response_model=AdminPaymentRead, status_code=status.HTTP_201_CREATED)
async def create_payment(
    payment_in: AdminPaymentCreate,
    session: DBSession,
) -> AdminPaymentRead:
    return await AdminFinanceService(session).create_payment(payment_in)


@router.patch("/payments/{payment_id}", response_model=AdminPaymentRead)
async def update_payment(
    payment_id: UUID,
    payment_in: AdminStudentPaymentUpdate,
    session: DBSession,
) -> AdminPaymentRead:
    return await AdminFinanceService(session).update_payment(payment_id, payment_in)


@router.delete("/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment(payment_id: UUID, session: DBSession) -> Response:
    await AdminFinanceService(session).delete_payment(payment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
