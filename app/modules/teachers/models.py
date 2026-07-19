from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Teacher(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teachers"
