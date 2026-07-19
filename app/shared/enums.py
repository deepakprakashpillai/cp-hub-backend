from enum import StrEnum


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
