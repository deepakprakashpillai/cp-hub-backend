from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.packages.models import Package
from app.modules.student_access_grants.models import StudentAccessGrant
from app.modules.student_access_grants.schemas import StudentAccessGrantCreate
from app.modules.students.models import Student
from app.modules.users.models import User
from app.shared.enums import StudentAccessGrantType
from app.shared.utils import utc_now


class StudentAccessGrantService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_grants(self, student_id: UUID | None = None) -> list[StudentAccessGrant]:
        query = select(StudentAccessGrant).order_by(StudentAccessGrant.created_at.desc())
        if student_id is not None:
            query = query.where(StudentAccessGrant.student_id == student_id)

        result = await self.session.scalars(query)
        return list(result)

    async def get_grant(self, grant_id: UUID) -> StudentAccessGrant:
        grant = await self.session.get(StudentAccessGrant, grant_id)
        if grant is None:
            raise NotFoundError("Student access grant not found")
        return grant

    async def create_grant(self, grant_in: StudentAccessGrantCreate) -> StudentAccessGrant:
        student = await self.session.get(Student, grant_in.student_id)
        if student is None:
            raise NotFoundError("Student not found")

        package = await self._get_package_for_grant(grant_in)
        duration_days = self._resolve_duration_days(grant_in, package)

        if grant_in.created_by_user_id is not None:
            user = await self.session.get(User, grant_in.created_by_user_id)
            if user is None:
                raise NotFoundError("User not found")

        now = utc_now()
        access_starts_at, access_ends_at = calculate_access_window(
            duration_days=duration_days,
            requested_starts_at=grant_in.access_starts_at,
            current_access_ends_at=student.access_ends_at,
            extend_current_access=grant_in.extend_current_access,
            now=now,
        )

        grant = StudentAccessGrant(
            student_id=grant_in.student_id,
            package_id=grant_in.package_id,
            grant_type=grant_in.grant_type,
            duration_days=duration_days,
            access_starts_at=access_starts_at,
            access_ends_at=access_ends_at,
            created_by_user_id=grant_in.created_by_user_id,
            notes=grant_in.notes,
        )
        student.access_starts_at = access_starts_at
        student.access_ends_at = access_ends_at

        self.session.add(grant)
        await self.session.commit()
        await self.session.refresh(grant)
        return grant

    async def _get_package_for_grant(
        self,
        grant_in: StudentAccessGrantCreate,
    ) -> Package | None:
        if grant_in.grant_type == StudentAccessGrantType.PACKAGE and grant_in.package_id is None:
            raise BadRequestError("Package grants must include package_id")

        if grant_in.package_id is None:
            return None

        package = await self.session.get(Package, grant_in.package_id)
        if package is None:
            raise NotFoundError("Package not found")

        if grant_in.grant_type == StudentAccessGrantType.PACKAGE and not package.is_active:
            raise BadRequestError("Cannot grant access from an inactive package")

        return package

    def _resolve_duration_days(
        self,
        grant_in: StudentAccessGrantCreate,
        package: Package | None,
    ) -> int:
        if grant_in.duration_days is not None:
            return grant_in.duration_days

        if package is not None:
            return package.duration_days

        raise BadRequestError("duration_days is required when no package duration is available")


def calculate_access_window(
    *,
    duration_days: int,
    requested_starts_at: datetime | None,
    current_access_ends_at: datetime | None,
    extend_current_access: bool,
    now: datetime,
) -> tuple[datetime, datetime]:
    now = _normalize_utc_datetime(now)

    if (
        extend_current_access
        and current_access_ends_at is not None
        and _normalize_utc_datetime(current_access_ends_at) > now
    ):
        access_starts_at = _normalize_utc_datetime(current_access_ends_at)
    elif requested_starts_at is not None:
        access_starts_at = _normalize_utc_datetime(requested_starts_at)
    else:
        access_starts_at = now

    first_counted_day = _first_counted_day_start(access_starts_at)
    access_ends_at = first_counted_day + timedelta(days=duration_days)
    return access_starts_at, access_ends_at


def _first_counted_day_start(access_starts_at: datetime) -> datetime:
    start_midnight = datetime.combine(access_starts_at.date(), time.min, tzinfo=UTC)
    if access_starts_at == start_midnight:
        return start_midnight
    return start_midnight + timedelta(days=1)


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone info")
    return value.astimezone(UTC)
