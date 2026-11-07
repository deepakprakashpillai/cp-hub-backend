from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


async def paginate_scalars[T](
    session: AsyncSession,
    statement: Select[tuple[T]],
    pagination: PaginationParams,
) -> Page[T]:
    total = await count_statement_rows(session, statement)
    result = await session.scalars(statement.offset(pagination.offset).limit(pagination.page_size))
    return Page(
        items=list(result),
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


async def paginate_rows(
    session: AsyncSession,
    statement: Select[Any],
    pagination: PaginationParams,
) -> tuple[list[Any], int]:
    total = await count_statement_rows(session, statement)
    result = await session.execute(statement.offset(pagination.offset).limit(pagination.page_size))
    return list(result.all()), total


async def count_statement_rows(session: AsyncSession, statement: Select[Any]) -> int:
    count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    return await session.scalar(count_statement) or 0
