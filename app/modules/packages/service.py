from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.packages.models import Package
from app.modules.packages.schemas import PackageCreate, PackageUpdate


class PackageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_packages(self) -> list[Package]:
        result = await self.session.scalars(select(Package).order_by(Package.created_at.desc()))
        return list(result)

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

        for field, value in update_data.items():
            setattr(package, field, value)

        await self.session.commit()
        await self.session.refresh(package)
        return package
