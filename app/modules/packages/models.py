from sqlalchemy import Boolean, Integer, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Package(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "packages"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default="INR",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
