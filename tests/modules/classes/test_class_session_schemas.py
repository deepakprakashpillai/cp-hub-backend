from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.modules.classes.schemas import BatchClassSessionCreate
from app.shared.enums import BatchSlot


def test_batch_class_session_create_normalizes_datetimes_to_utc() -> None:
    class_session = BatchClassSessionCreate(
        batch_slot=BatchSlot.MORNING,
        starts_at=datetime.fromisoformat("2026-07-20T08:00:00+05:30"),
        ends_at=datetime.fromisoformat("2026-07-20T09:00:00+05:30"),
        capacity=20,
    )

    assert class_session.starts_at == datetime(2026, 7, 20, 2, 30, tzinfo=UTC)
    assert class_session.ends_at == datetime(2026, 7, 20, 3, 30, tzinfo=UTC)


def test_batch_class_session_create_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError, match="datetime must include timezone info"):
        BatchClassSessionCreate(
            batch_slot=BatchSlot.NOON,
            starts_at=datetime(2026, 7, 20, 12, 0),
            ends_at=datetime(2026, 7, 20, 13, 0, tzinfo=UTC),
            capacity=20,
        )


def test_batch_class_session_create_rejects_invalid_time_range() -> None:
    with pytest.raises(ValidationError, match="starts_at must be before ends_at"):
        BatchClassSessionCreate(
            batch_slot=BatchSlot.AFTERNOON,
            starts_at=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
            ends_at=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
            capacity=20,
        )
