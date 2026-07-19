from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ClassSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "class_sessions"
