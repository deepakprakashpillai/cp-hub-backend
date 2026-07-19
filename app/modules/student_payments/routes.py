from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DBSession
from app.modules.student_payments.schemas import (
    StudentPaymentCreate,
    StudentPaymentRead,
    StudentPaymentUpdate,
)
from app.modules.student_payments.service import StudentPaymentService

router = APIRouter()


@router.get("", response_model=list[StudentPaymentRead])
async def list_student_payments(
    session: DBSession,
    student_id: UUID | None = None,
) -> list[StudentPaymentRead]:
    return await StudentPaymentService(session).list_payments(student_id=student_id)


@router.post("", response_model=StudentPaymentRead, status_code=status.HTTP_201_CREATED)
async def create_student_payment(
    payment_in: StudentPaymentCreate,
    session: DBSession,
) -> StudentPaymentRead:
    return await StudentPaymentService(session).create_payment(payment_in)


@router.get("/{payment_id}", response_model=StudentPaymentRead)
async def get_student_payment(
    payment_id: UUID,
    session: DBSession,
) -> StudentPaymentRead:
    return await StudentPaymentService(session).get_payment(payment_id)


@router.patch("/{payment_id}", response_model=StudentPaymentRead)
async def update_student_payment(
    payment_id: UUID,
    payment_in: StudentPaymentUpdate,
    session: DBSession,
) -> StudentPaymentRead:
    return await StudentPaymentService(session).update_payment(payment_id, payment_in)


@router.delete("/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student_payment(
    payment_id: UUID,
    session: DBSession,
) -> None:
    await StudentPaymentService(session).delete_payment(payment_id)
