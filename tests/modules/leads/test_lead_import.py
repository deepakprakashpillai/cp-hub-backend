import io
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.core.exceptions import BadRequestError
from app.modules.leads.models import Lead
from app.modules.leads.schemas import LeadConvert
from app.modules.leads.service import LeadService
from app.modules.students.service import StudentService
from app.modules.users.service import UserService
from app.shared.enums import LeadStatus, StudentProgramType


@pytest.mark.asyncio
async def test_csv_import_accepts_human_headers_and_defaults_blank_status() -> None:
    service = LeadService(None)  # type: ignore[arg-type]
    file = UploadFile(
        filename="leads.csv",
        file=io.BytesIO(
            b"Full Name,Email,Phone,Source,Status\n"
            b"Ada Lovelace,ADA@example.com,+91 999 123 4567,Referral,\n"
        ),
    )

    rows, issues = await service._read_import_rows(file)

    assert issues == []
    assert rows == [
        (
            2,
            {
                "full_name": "Ada Lovelace",
                "email": "ada@example.com",
                "phone": "919991234567",
                "source": "Referral",
                "status": LeadStatus.NEW,
            },
        )
    ]


def test_import_row_rejects_lead_without_contact_details() -> None:
    service = LeadService(None)  # type: ignore[arg-type]

    with pytest.raises(BadRequestError, match="email or phone"):
        service._normalize_import_row(["Ada Lovelace"], {"full_name": 0})


def test_import_status_accepts_human_label() -> None:
    service = LeadService(None)  # type: ignore[arg-type]

    row = service._normalize_import_row(
        ["Ada Lovelace", "ada@example.com", "Trial booked"],
        {"full_name": 0, "email": 1, "status": 2},
    )

    assert row["status"] == LeadStatus.TRIAL_BOOKED


@pytest.mark.asyncio
async def test_enrolled_lead_conversion_creates_linked_student(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    lead = Lead(
        id=uuid4(),
        full_name="Ada Lovelace",
        email=None,
        phone="919991234567",
        source="Referral",
        status=LeadStatus.ENROLLED,
        created_at=datetime(2026, 7, 26, tzinfo=UTC),
        updated_at=datetime(2026, 7, 26, tzinfo=UTC),
    )
    student_id = uuid4()
    user_calls = {}

    async def fake_get_lead(self, lead_id):
        assert lead_id == lead.id
        return lead

    async def fake_duplicate_check(self, email, phone, *, exclude_id=None):
        assert email == "ada@example.com"
        assert phone == lead.phone
        assert exclude_id == lead.id

    async def fake_create_user(self, user_in, *, commit=True):
        user_calls["email"] = user_in.email
        user_calls["commit"] = commit
        return SimpleNamespace(id=uuid4())

    async def fake_create_student(self, student_in, *, commit=True):
        user_calls["program_type"] = student_in.program_type
        user_calls["student_commit"] = commit
        return SimpleNamespace(id=student_id)

    monkeypatch.setattr(LeadService, "get_lead", fake_get_lead)
    monkeypatch.setattr(LeadService, "_ensure_not_duplicate", fake_duplicate_check)
    monkeypatch.setattr(UserService, "create_user", fake_create_user)
    monkeypatch.setattr(StudentService, "create_student", fake_create_student)

    result = await LeadService(session).convert_lead(
        lead.id,
        LeadConvert(email="ADA@example.com", program_type=StudentProgramType.BATCH),
    )

    assert result.student_id == student_id
    assert lead.converted_student_id == student_id
    assert lead.email == "ada@example.com"
    assert user_calls == {
        "email": "ada@example.com",
        "commit": False,
        "program_type": StudentProgramType.BATCH,
        "student_commit": False,
    }
    session.commit.assert_awaited_once()
