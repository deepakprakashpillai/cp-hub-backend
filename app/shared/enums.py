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


class StudentStatus(StrEnum):
    ENROLLED = "enrolled"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentMethod(StrEnum):
    UPI = "upi"
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    OTHER = "other"


class StudentAccessGrantType(StrEnum):
    PACKAGE = "package"
    ADDON_DAYS = "addon_days"
    MANUAL_ADJUSTMENT = "manual_adjustment"


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


class BookingEventType(StrEnum):
    BOOKED = "booked"
    CANCELLED_BY_STUDENT = "cancelled_by_student"
    CANCELLED_BY_ADMIN = "cancelled_by_admin"
    RESCHEDULED_FROM = "rescheduled_from"
    RESCHEDULED_TO = "rescheduled_to"
    CLASS_CANCELLED_EMPTY = "class_cancelled_empty"
    ATTENDANCE_MARKED = "attendance_marked"
    MANUALLY_ADDED_BY_ADMIN = "manually_added_by_admin"


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    TRIAL_BOOKED = "trial_booked"
    ENROLLED = "enrolled"
    LOST = "lost"
