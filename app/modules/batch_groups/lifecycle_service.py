from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_scalars
from app.modules.batch_groups._shared import _BatchGroupShared
from app.modules.batch_groups.models import BatchGroup
from app.modules.batch_groups.schemas import (
    BatchGroupCreate,
    BatchGroupUpdate,
)
from app.shared.enums import (
    DayOfWeek,
)

DAY_TO_INDEX = {
    DayOfWeek.MONDAY: 0,
    DayOfWeek.TUESDAY: 1,
    DayOfWeek.WEDNESDAY: 2,
    DayOfWeek.THURSDAY: 3,
    DayOfWeek.FRIDAY: 4,
    DayOfWeek.SATURDAY: 5,
    DayOfWeek.SUNDAY: 6,
}


class BatchGroupLifecycleService(_BatchGroupShared):
    async def list_batch_groups(
        self,
        pagination: PaginationParams,
        is_active: bool | None = None,
    ) -> Page:
        statement = select(BatchGroup).order_by(BatchGroup.created_at.desc())
        if is_active is not None:
            statement = statement.where(BatchGroup.is_active.is_(is_active))

        return await paginate_scalars(self.session, statement, pagination)

    async def get_batch_group(self, batch_group_id: UUID) -> BatchGroup:
        batch_group = await self.session.get(BatchGroup, batch_group_id)
        if batch_group is None:
            raise NotFoundError("Batch group not found")
        return batch_group

    async def create_batch_group(self, batch_group_in: BatchGroupCreate) -> BatchGroup:
        if batch_group_in.is_active:
            await self._ensure_active_name_available(batch_group_in.name)
            if batch_group_in.package_id is None:
                raise ConflictError("An active batch group requires a package")
        if batch_group_in.package_id is not None:
            await self._get_package(
                batch_group_in.package_id,
                require_active=batch_group_in.is_active,
            )

        batch_group = BatchGroup(**batch_group_in.model_dump())
        self.session.add(batch_group)
        await self.session.commit()
        await self.session.refresh(batch_group)
        return batch_group

    async def update_batch_group(
        self,
        batch_group_id: UUID,
        batch_group_in: BatchGroupUpdate,
    ) -> BatchGroup:
        batch_group = await self.get_batch_group(batch_group_id)
        update_data = batch_group_in.model_dump(exclude_unset=True)

        for non_nullable_field in ("name", "default_capacity", "is_active"):
            if non_nullable_field in update_data and update_data[non_nullable_field] is None:
                raise BadRequestError(f"{non_nullable_field} cannot be null")

        final_name = update_data.get("name", batch_group.name)
        final_is_active = update_data.get("is_active", batch_group.is_active)
        if final_is_active:
            await self._ensure_active_name_available(
                final_name,
                exclude_batch_group_id=batch_group.id,
            )
        package_changed = "package_id" in update_data
        final_package_id = update_data.get("package_id", batch_group.package_id)
        activating = final_is_active and not batch_group.is_active
        if final_is_active and final_package_id is None and (package_changed or activating):
            raise ConflictError("An active batch group requires a package")
        if final_package_id is not None and (package_changed or activating):
            await self._get_package(final_package_id, require_active=final_is_active)

        for field, value in update_data.items():
            setattr(batch_group, field, value)

        if batch_group.is_active is False:
            await self._cancel_future_group_activity(batch_group.id)

        await self.session.commit()
        await self.session.refresh(batch_group)
        return batch_group

    async def void_batch_group(self, batch_group_id: UUID) -> BatchGroup:
        batch_group = await self.get_batch_group(batch_group_id)
        batch_group.is_active = False
        await self._cancel_future_group_activity(batch_group.id)
        await self.session.commit()
        await self.session.refresh(batch_group)
        return batch_group
