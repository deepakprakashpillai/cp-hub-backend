from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Query

from app.modules.admin.schemas import (
    AdminBatchGroupSortBy,
    AdminPackageSortBy,
    AdminPaymentSortBy,
    AdminStudentAccessState,
    AdminStudentSortBy,
    AdminTeacherSortBy,
    SortOrder,
)
from app.shared.enums import (
    AvailabilitySlotSource,
    AvailabilitySlotStatus,
    BookingStatus,
    ClassSessionStatus,
    PaymentMethod,
    StudentProgramType,
    StudentStatus,
)

DatetimeQuery = Annotated[datetime | None, Query()]
DateQuery = Annotated[date | None, Query()]
ProgramTypeQuery = Annotated[StudentProgramType | None, Query()]
IsActiveQuery = Annotated[bool | None, Query()]
SearchQuery = Annotated[str | None, Query(max_length=150)]
StudentStatusQuery = Annotated[StudentStatus | None, Query()]
StudentAccessStateQuery = Annotated[AdminStudentAccessState | None, Query()]
StudentSortByQuery = Annotated[AdminStudentSortBy, Query()]
TeacherSortByQuery = Annotated[AdminTeacherSortBy, Query()]
BatchGroupSortByQuery = Annotated[AdminBatchGroupSortBy, Query()]
PackageSortByQuery = Annotated[AdminPackageSortBy, Query()]
PaymentSortByQuery = Annotated[AdminPaymentSortBy, Query()]
SortOrderQuery = Annotated[SortOrder, Query()]
PaymentMethodQuery = Annotated[PaymentMethod | None, Query()]
CurrencyQuery = Annotated[str | None, Query(min_length=3, max_length=3)]
AvailabilitySlotStatusQuery = Annotated[AvailabilitySlotStatus | None, Query()]
AvailabilitySlotSourceQuery = Annotated[AvailabilitySlotSource | None, Query()]
ClassSessionStatusQuery = Annotated[ClassSessionStatus | None, Query()]
BookingStatusQuery = Annotated[BookingStatus | None, Query()]
TeacherIdQuery = Annotated[UUID | None, Query()]
DaysAheadQuery = Annotated[int, Query(ge=1, le=90)]
ReasonQuery = Annotated[str | None, Query(max_length=1000)]
