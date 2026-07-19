from datetime import UTC, datetime

from app.modules.student_access_grants.service import calculate_access_window


def test_fresh_access_grant_counts_tomorrow_as_day_one() -> None:
    now = datetime(2026, 7, 19, 14, 30, tzinfo=UTC)

    starts_at, ends_at = calculate_access_window(
        duration_days=1,
        requested_starts_at=None,
        current_access_ends_at=None,
        extend_current_access=True,
        now=now,
    )

    assert starts_at == now
    assert ends_at == datetime(2026, 7, 21, 0, 0, tzinfo=UTC)


def test_midnight_start_counts_same_day_as_day_one() -> None:
    starts_at, ends_at = calculate_access_window(
        duration_days=30,
        requested_starts_at=datetime(2026, 7, 20, 0, 0, tzinfo=UTC),
        current_access_ends_at=None,
        extend_current_access=False,
        now=datetime(2026, 7, 19, 14, 30, tzinfo=UTC),
    )

    assert starts_at == datetime(2026, 7, 20, 0, 0, tzinfo=UTC)
    assert ends_at == datetime(2026, 8, 19, 0, 0, tzinfo=UTC)


def test_access_grant_extends_from_current_future_access_end() -> None:
    current_access_ends_at = datetime(2026, 8, 19, 0, 0, tzinfo=UTC)

    starts_at, ends_at = calculate_access_window(
        duration_days=10,
        requested_starts_at=None,
        current_access_ends_at=current_access_ends_at,
        extend_current_access=True,
        now=datetime(2026, 7, 19, 14, 30, tzinfo=UTC),
    )

    assert starts_at == current_access_ends_at
    assert ends_at == datetime(2026, 8, 29, 0, 0, tzinfo=UTC)


def test_access_grant_can_start_fresh_instead_of_extending() -> None:
    requested_starts_at = datetime(2026, 7, 22, 0, 0, tzinfo=UTC)

    starts_at, ends_at = calculate_access_window(
        duration_days=5,
        requested_starts_at=requested_starts_at,
        current_access_ends_at=datetime(2026, 8, 19, 0, 0, tzinfo=UTC),
        extend_current_access=False,
        now=datetime(2026, 7, 19, 14, 30, tzinfo=UTC),
    )

    assert starts_at == requested_starts_at
    assert ends_at == datetime(2026, 7, 27, 0, 0, tzinfo=UTC)
