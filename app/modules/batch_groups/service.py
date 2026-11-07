from app.modules.batch_groups._shared import build_utc_session_datetimes
from app.modules.batch_groups.lifecycle_service import BatchGroupLifecycleService
from app.modules.batch_groups.membership_service import BatchMembershipService
from app.modules.batch_groups.session_generation_service import BatchSessionGenerationService


class _BatchGroupOperations(
    BatchGroupLifecycleService,
    BatchMembershipService,
    BatchSessionGenerationService,
):
    """Test-only composite for low-level invariant coverage."""


__all__ = [
    "BatchGroupLifecycleService",
    "BatchMembershipService",
    "BatchSessionGenerationService",
    "build_utc_session_datetimes",
]
