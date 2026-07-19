from enum import StrEnum


def enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_class]


class UserRole(StrEnum):
    ADMIN = "admin"
    STUDENT = "student"
    TEACHER = "teacher"
    LEAD_MANAGER = "lead_manager"


class StudentProgramType(StrEnum):
    ONE_ON_ONE = "one_on_one"
    BATCH = "batch"


class BatchSlot(StrEnum):
    MORNING = "morning"
    NOON = "noon"
    AFTERNOON = "afternoon"


class DayOfWeek(StrEnum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class AvailabilitySlotSource(StrEnum):
    RULE = "rule"
    MANUAL = "manual"


class AvailabilitySlotStatus(StrEnum):
    AVAILABLE = "available"
    BOOKED = "booked"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class ClassSessionStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BookingStatus(StrEnum):
    BOOKED = "booked"
    CANCELLED = "cancelled"
    ATTENDED = "attended"
    MISSED = "missed"


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    TRIAL_BOOKED = "trial_booked"
    ENROLLED = "enrolled"
    LOST = "lost"
