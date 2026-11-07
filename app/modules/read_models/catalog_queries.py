from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, PaginationParams, paginate_rows
from app.modules.batch_groups.models import BatchGroup, StudentBatchMembership
from app.modules.classes.models import ClassSession
from app.modules.read_models.admin_schemas import (
    AdminBatchGroupRead,
    AdminBatchGroupSortBy,
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


class AdminCatalogQueryService(_ServiceBase):
    async def list_batch_groups(
        self,
        pagination: PaginationParams,
        is_active: bool | None = None,
        q: str | None = None,
        sort_by: AdminBatchGroupSortBy = AdminBatchGroupSortBy.CREATED_AT,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> Page:
        now = utc_now()
        active_members = (
            select(
                StudentBatchMembership.batch_group_id.label("batch_group_id"),
                func.count().label("active_member_count"),
            )
            .where(StudentBatchMembership.is_active.is_(True))
            .group_by(StudentBatchMembership.batch_group_id)
            .subquery()
        )

        upcoming_sessions = (
            select(
                ClassSession.batch_group_id.label("batch_group_id"),
                func.count().label("upcoming_scheduled_count"),
            )
            .where(
                ClassSession.status == ClassSessionStatus.SCHEDULED,
                ClassSession.starts_at > now,
            )
            .group_by(ClassSession.batch_group_id)
            .subquery()
        )
        active_member_count = func.coalesce(active_members.c.active_member_count, 0)
        upcoming_scheduled_count = func.coalesce(
            upcoming_sessions.c.upcoming_scheduled_count,
            0,
        )
        sort_columns = {
            AdminBatchGroupSortBy.CREATED_AT: BatchGroup.created_at,
            AdminBatchGroupSortBy.NAME: BatchGroup.name,
            AdminBatchGroupSortBy.ACTIVE_MEMBER_COUNT: active_member_count,
            AdminBatchGroupSortBy.UPCOMING_SCHEDULED_COUNT: upcoming_scheduled_count,
            AdminBatchGroupSortBy.IS_ACTIVE: BatchGroup.is_active,
        }
        sort_column = sort_columns[sort_by]
        order_expression = sort_column.asc() if sort_order == SortOrder.ASC else sort_column.desc()
        statement = (
            select(
                BatchGroup,
                active_member_count.label("active_member_count"),
                upcoming_scheduled_count.label("upcoming_scheduled_count"),
            )
            .outerjoin(
                active_members,
                active_members.c.batch_group_id == BatchGroup.id,
            )
            .outerjoin(
                upcoming_sessions,
                upcoming_sessions.c.batch_group_id == BatchGroup.id,
            )
            .order_by(order_expression, BatchGroup.id.asc())
        )
        if is_active is not None:
            statement = statement.where(BatchGroup.is_active.is_(is_active))
        normalized_q = _normalize_search_query(q)
        if normalized_q is not None:
            statement = statement.where(BatchGroup.name.ilike(f"%{normalized_q}%"))

        rows, total = await paginate_rows(self.session, statement, pagination)
        return Page(
            items=[
                AdminBatchGroupRead.model_validate(
                    {
                        **_model_values(batch_group),
                        "package": batch_group.package,
                        "active_member_count": active_count,
                        "upcoming_scheduled_count": upcoming_count,
                    }
                )
                for batch_group, active_count, upcoming_count in rows
            ],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )


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
