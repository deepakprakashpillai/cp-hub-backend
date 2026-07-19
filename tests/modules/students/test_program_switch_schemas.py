import pytest
from pydantic import ValidationError

from app.modules.students.schemas import StudentProgramSwitch
from app.shared.enums import StudentProgramType


def test_student_program_switch_accepts_reason() -> None:
    switch = StudentProgramSwitch(
        new_program_type=StudentProgramType.BATCH,
        reason="Student is moving into daily batch classes.",
    )

    assert switch.new_program_type == StudentProgramType.BATCH
    assert switch.reason == "Student is moving into daily batch classes."


def test_student_program_switch_rejects_long_reason() -> None:
    with pytest.raises(ValidationError):
        StudentProgramSwitch(
            new_program_type=StudentProgramType.ONE_ON_ONE,
            reason="x" * 1001,
        )
