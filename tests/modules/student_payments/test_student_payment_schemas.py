from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.student_payments.schemas import StudentPaymentCreate, StudentPaymentUpdate
from app.shared.enums import PaymentMethod


def test_student_payment_create_defaults_currency_and_paid_at() -> None:
    payment = StudentPaymentCreate(
        student_id=uuid4(),
        amount_paid=500000,
        payment_method=PaymentMethod.UPI,
    )

    assert payment.currency == "INR"
    assert payment.paid_at.tzinfo is not None


def test_student_payment_create_normalizes_paid_at_to_utc() -> None:
    payment = StudentPaymentCreate(
        student_id=uuid4(),
        amount_paid=500000,
        payment_method=PaymentMethod.CASH,
        paid_at=datetime.fromisoformat("2026-07-19T14:30:00+05:30"),
    )

    assert payment.paid_at == datetime(2026, 7, 19, 9, 0, tzinfo=UTC)


def test_student_payment_create_rejects_naive_paid_at() -> None:
    with pytest.raises(ValidationError, match="datetime must include timezone info"):
        StudentPaymentCreate(
            student_id=uuid4(),
            amount_paid=500000,
            payment_method=PaymentMethod.BANK_TRANSFER,
            paid_at=datetime(2026, 7, 19, 14, 30),
        )


def test_student_payment_create_rejects_negative_amount() -> None:
    with pytest.raises(ValidationError):
        StudentPaymentCreate(
            student_id=uuid4(),
            amount_paid=-1,
            payment_method=PaymentMethod.OTHER,
        )


def test_student_payment_update_normalizes_paid_at_to_utc() -> None:
    payment = StudentPaymentUpdate(
        paid_at=datetime.fromisoformat("2026-07-19T14:30:00+05:30"),
    )

    assert payment.paid_at == datetime(2026, 7, 19, 9, 0, tzinfo=UTC)


def test_student_payment_update_rejects_negative_amount() -> None:
    with pytest.raises(ValidationError):
        StudentPaymentUpdate(amount_paid=-1)
