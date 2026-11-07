from app.modules.bookings.attendance_service import BookingAttendanceService
from app.modules.bookings.cancellation_service import BookingCancellationService
from app.modules.bookings.creation_service import BookingCreationService
from app.modules.bookings.query_service import BookingQueryService
from app.modules.bookings.reschedule_service import BookingRescheduleService


class _BookingOperations(
    BookingQueryService,
    BookingCreationService,
    BookingCancellationService,
    BookingRescheduleService,
    BookingAttendanceService,
):
    """Test-only composite for low-level invariant coverage."""


__all__ = [
    "BookingQueryService",
    "BookingCreationService",
    "BookingCancellationService",
    "BookingRescheduleService",
    "BookingAttendanceService",
]
