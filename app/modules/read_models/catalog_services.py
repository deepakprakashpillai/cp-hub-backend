from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_rows
from app.modules.batch_groups.models import BatchGroup, StudentBatchMembership
from app.modules.batch_groups.schemas import (
    BatchGroupCreate,
    BatchGroupUpdate,
    StudentBatchMembershipAssign,
)
from app.modules.batch_groups.service import (
    BatchGroupLifecycleService,
    BatchMembershipService,
)
from app.modules.classes.models import ClassSession
from app.modules.packages.models import Package
from app.modules.packages.schemas import PackageCreate, PackageUpdate
from app.modules.packages.service import PackageService
from app.modules.read_models.admin_schemas import (
    AdminBatchGroupRead,
    AdminPackageSortBy,
    AdminStudentAccessState,
)
from app.modules.students.models import Student
from app.shared.enums import (
    ClassSessionStatus,
    SortOrder,
)
from app.shared.utils import utc_now


class _ServiceBase:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


class AdminCatalogService(_ServiceBase):
    async def create_batch_group(self, batch_group_in: BatchGroupCreate) -> BatchGroup:
        return await BatchGroupLifecycleService(self.session).create_batch_group(batch_group_in)

    async def get_batch_group(self, batch_group_id: UUID) -> AdminBatchGroupRead:
        now = utc_now()
        row = (
            await self.session.execute(
                select(
                    BatchGroup,
                    select(func.count())
                    .select_from(StudentBatchMembership)
                    .where(
                        StudentBatchMembership.batch_group_id == BatchGroup.id,
                        StudentBatchMembership.is_active.is_(True),
                    )
                    .correlate(BatchGroup)
                    .scalar_subquery()
                    .label("active_member_count"),
                    select(func.count())
                    .select_from(ClassSession)
                    .where(
                        ClassSession.batch_group_id == BatchGroup.id,
                        ClassSession.status == ClassSessionStatus.SCHEDULED,
                        ClassSession.starts_at > now,
                    )
                    .correlate(BatchGroup)
                    .scalar_subquery()
                    .label("upcoming_scheduled_count"),
                ).where(BatchGroup.id == batch_group_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Batch group not found")
        batch_group, active_count, upcoming_count = row
        return AdminBatchGroupRead.model_validate(
            {
                **_model_values(batch_group),
                "package": batch_group.package,
                "active_member_count": active_count,
                "upcoming_scheduled_count": upcoming_count,
            }
        )

    async def update_batch_group(
        self,
        batch_group_id: UUID,
        batch_group_in: BatchGroupUpdate,
    ) -> BatchGroup:
        return await BatchGroupLifecycleService(self.session).update_batch_group(
            batch_group_id,
            batch_group_in,
        )

    async def void_batch_group(self, batch_group_id: UUID) -> BatchGroup:
        return await BatchGroupLifecycleService(self.session).void_batch_group(batch_group_id)

    async def list_batch_group_students(
        self,
        batch_group_id: UUID,
        pagination: PaginationParams,
        is_active: bool | None = True,
    ) -> Page:
        return await BatchMembershipService(self.session).list_batch_group_students(
            batch_group_id=batch_group_id,
            pagination=pagination,
            is_active=is_active,
        )

    async def add_student_to_batch_group(
        self,
        batch_group_id: UUID,
        membership_in: StudentBatchMembershipAssign,
    ) -> StudentBatchMembership:
        return await BatchMembershipService(self.session).assign_student_to_batch_group(
            batch_group_id,
            membership_in,
        )

    async def remove_student_from_batch_group(
        self,
        batch_group_id: UUID,
        student_id: UUID,
        *,
        reason: str | None,
    ) -> StudentBatchMembership:
        return await BatchMembershipService(self.session).remove_student_from_batch_group(
            batch_group_id,
            student_id,
            reason=reason,
        )

    async def list_packages(
        self,
        pagination: PaginationParams,
        *,
        q: str | None = None,
        is_active: bool | None = None,
        sort_by: AdminPackageSortBy = AdminPackageSortBy.CREATED_AT,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> Page:
        sort_columns = {
            AdminPackageSortBy.CREATED_AT: Package.created_at,
            AdminPackageSortBy.NAME: Package.name,
            AdminPackageSortBy.DURATION_DAYS: Package.duration_days,
            AdminPackageSortBy.PRICE_AMOUNT: Package.price_amount,
            AdminPackageSortBy.IS_ACTIVE: Package.is_active,
        }
        sort_column = sort_columns[sort_by]
        order_expression = sort_column.asc() if sort_order == SortOrder.ASC else sort_column.desc()
        statement = select(Package).order_by(order_expression, Package.id.asc())
        normalized_q = _normalize_search_query(q)
        if normalized_q is not None:
            statement = statement.where(Package.name.ilike(f"%{normalized_q}%"))
        if is_active is not None:
            statement = statement.where(Package.is_active.is_(is_active))
        rows, total = await paginate_rows(self.session, statement, pagination)
        return Page(
            items=[row[0] for row in rows],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def create_package(self, package_in: PackageCreate) -> Package:
        return await PackageService(self.session).create_package(package_in)

    async def get_package(self, package_id: UUID) -> Package:
        return await PackageService(self.session).get_package(package_id)

    async def update_package(self, package_id: UUID, package_in: PackageUpdate) -> Package:
        return await PackageService(self.session).update_package(package_id, package_in)

    async def void_package(self, package_id: UUID) -> Package:
        return await PackageService(self.session).void_package(package_id)


def _resolve_dashboard_window(
    *,
    starts_from: datetime | None,
    starts_to: datetime | None,
    now: datetime,
) -> tuple[datetime, datetime]:
    if starts_from is None:
        starts_from = datetime.combine(now.date(), time.min, tzinfo=UTC)
    if starts_to is None:
        starts_to = starts_from + timedelta(days=1)
    if starts_from >= starts_to:
        raise ValueError("starts_from must be before starts_to")
    return starts_from, starts_to


def _normalize_search_query(q: str | None) -> str | None:
    if q is None:
        return None
    normalized = q.strip()
    return normalized or None


def _model_values(model) -> dict:
    return {key: value for key, value in vars(model).items() if not key.startswith("_")}


def _student_access_state_clause(access_state: AdminStudentAccessState, now: datetime):
    if access_state == AdminStudentAccessState.VALID:
        return (
            Student.access_starts_at.is_not(None)
            & (Student.access_starts_at <= now)
            & Student.access_ends_at.is_not(None)
            & (Student.access_ends_at > now)
        )
    if access_state == AdminStudentAccessState.EXPIRED:
        return Student.access_ends_at.is_not(None) & (Student.access_ends_at <= now)
    if access_state == AdminStudentAccessState.NOT_STARTED:
        return Student.access_starts_at.is_not(None) & (Student.access_starts_at > now)
    return or_(Student.access_starts_at.is_(None), Student.access_ends_at.is_(None))
