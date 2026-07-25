from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_scalars
from app.modules.batch_groups.models import BatchGroup
from app.modules.packages.models import Package
from app.modules.packages.schemas import PackageCreate, PackageUpdate


class PackageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_packages(self, pagination: PaginationParams) -> Page:
        return await paginate_scalars(
            self.session,
            select(Package).order_by(Package.created_at.desc()),
            pagination,
        )

    async def get_package(self, package_id: UUID) -> Package:
        package = await self.session.get(Package, package_id)
        if package is None:
            raise NotFoundError("Package not found")
        return package

    async def create_package(self, package_in: PackageCreate) -> Package:
        package = Package(**package_in.model_dump())
        self.session.add(package)
        await self.session.commit()
        await self.session.refresh(package)
        return package

    async def update_package(self, package_id: UUID, package_in: PackageUpdate) -> Package:
        package = await self.get_package(package_id)
        update_data = package_in.model_dump(exclude_unset=True)

        for non_nullable_field in (
            "name",
            "duration_days",
            "price_amount",
            "currency",
            "is_active",
        ):
            if non_nullable_field in update_data and update_data[non_nullable_field] is None:
                raise BadRequestError(f"{non_nullable_field} cannot be null")
        if update_data.get("is_active") is False:
            await self._ensure_not_linked_to_active_batch_groups(package.id)

        for field, value in update_data.items():
            setattr(package, field, value)

        await self.session.commit()
        await self.session.refresh(package)
        return package

    async def void_package(self, package_id: UUID) -> Package:
        package = await self.get_package(package_id)
        await self._ensure_not_linked_to_active_batch_groups(package.id)
        package.is_active = False
        await self.session.commit()
        await self.session.refresh(package)
        return package

    async def _ensure_not_linked_to_active_batch_groups(self, package_id: UUID) -> None:
        active_group_id = await self.session.scalar(
            select(BatchGroup.id).where(
                BatchGroup.package_id == package_id,
                BatchGroup.is_active.is_(True),
            )
        )
        if active_group_id is not None:
            raise ConflictError("Package is linked to an active batch group")
