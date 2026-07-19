from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TeacherAvailabilitySlot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teacher_availability_slots"


class BatchScheduleSlot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "batch_schedule_slots"
