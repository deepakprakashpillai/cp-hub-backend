import csv
import io
import re
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from openpyxl import load_workbook
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_scalars
from app.modules.leads.models import Lead
from app.modules.leads.schemas import (
    LeadConversionRead,
    LeadConvert,
    LeadCreate,
    LeadImportIssue,
    LeadImportPreview,
    LeadImportResult,
    LeadSummary,
    LeadUpdate,
)
from app.modules.students.schemas import StudentCreate
from app.modules.students.service import StudentService
from app.modules.users.schemas import UserCreate
from app.modules.users.service import UserService
from app.shared.enums import LeadStatus, StudentStatus, UserRole
from app.shared.utils import utc_now


class LeadService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_leads(
        self,
        pagination: PaginationParams,
        *,
        q: str | None = None,
        status: LeadStatus | None = None,
    ) -> Page:
        statement = select(Lead).order_by(Lead.created_at.desc())
        if q:
            search = f"%{q.strip()}%"
            statement = statement.where(
                or_(
                    Lead.full_name.ilike(search),
                    Lead.email.ilike(search),
                    Lead.phone.ilike(search),
                    Lead.source.ilike(search),
                )
            )
        if status is not None:
            statement = statement.where(Lead.status == status)
        return await paginate_scalars(self.session, statement, pagination)

    async def create_lead(self, lead_in: LeadCreate) -> Lead:
        values = self._normalize_values(lead_in.model_dump())
        self._ensure_contact(values)
        await self._ensure_not_duplicate(values["email"], values["phone"])
        lead = Lead(**values)
        self.session.add(lead)
        await self.session.commit()
        await self.session.refresh(lead)
        return lead

    async def get_summary(self) -> LeadSummary:
        result = await self.session.execute(
            select(Lead.status, func.count(Lead.id)).group_by(Lead.status)
        )
        counts = {status: count for status, count in result}
        return LeadSummary(
            total=sum(counts.values()),
            new=counts.get(LeadStatus.NEW, 0),
            contacted=counts.get(LeadStatus.CONTACTED, 0),
            trial_booked=counts.get(LeadStatus.TRIAL_BOOKED, 0),
            enrolled=counts.get(LeadStatus.ENROLLED, 0),
            lost=counts.get(LeadStatus.LOST, 0),
        )

    async def update_lead(self, lead_id: UUID, lead_in: LeadUpdate) -> Lead:
        lead = await self.get_lead(lead_id)
        updates = self._normalize_values(lead_in.model_dump(exclude_unset=True))
        if "full_name" in updates and updates["full_name"] is None:
            raise BadRequestError("full_name cannot be null")

        final_values = {
            "full_name": updates.get("full_name", lead.full_name),
            "email": updates.get("email", lead.email),
            "phone": updates.get("phone", lead.phone),
        }
        self._ensure_contact(final_values)
        await self._ensure_not_duplicate(
            final_values["email"],
            final_values["phone"],
            exclude_id=lead.id,
        )
        for field, value in updates.items():
            setattr(lead, field, value)
        await self.session.commit()
        await self.session.refresh(lead)
        return lead

    async def delete_lead(self, lead_id: UUID) -> None:
        lead = await self.get_lead(lead_id)
        await self.session.delete(lead)
        await self.session.commit()

    async def convert_lead(self, lead_id: UUID, conversion: LeadConvert) -> LeadConversionRead:
        lead = await self.get_lead(lead_id)
        if lead.status != LeadStatus.ENROLLED:
            raise ConflictError("Only enrolled leads can be converted")
        if lead.converted_student_id is not None:
            raise ConflictError("Lead has already been converted")

        email = str(conversion.email).strip().lower()
        await self._ensure_not_duplicate(email, lead.phone, exclude_id=lead.id)
        user = await UserService(self.session).create_user(
            UserCreate(
                full_name=lead.full_name,
                email=email,
                phone=lead.phone,
                role=UserRole.STUDENT,
            ),
            commit=False,
        )
        student = await StudentService(self.session).create_student(
            StudentCreate(
                user_id=user.id,
                program_type=conversion.program_type,
                status=StudentStatus.ENROLLED,
            ),
            commit=False,
        )
        lead.email = email
        lead.converted_student_id = student.id
        lead.converted_at = utc_now()
        await self.session.commit()
        await self.session.refresh(lead)
        return LeadConversionRead(lead=lead, student_id=student.id)

    async def get_lead(self, lead_id: UUID) -> Lead:
        lead = await self.session.get(Lead, lead_id)
        if lead is None:
            raise NotFoundError("Lead not found")
        return lead

    async def preview_import(self, file: UploadFile) -> LeadImportPreview:
        rows, parsing_issues = await self._read_import_rows(file)
        valid, duplicate_issues = await self._split_import_rows(rows)
        issues = parsing_issues + duplicate_issues
        return LeadImportPreview(
            total_rows=len(rows) + len(parsing_issues),
            valid_rows=len(valid),
            duplicate_rows=len(duplicate_issues),
            invalid_rows=len(parsing_issues),
            issues=issues,
        )

    async def import_leads(self, file: UploadFile) -> LeadImportResult:
        rows, parsing_issues = await self._read_import_rows(file)
        valid, duplicate_issues = await self._split_import_rows(rows)
        for row in valid:
            self.session.add(Lead(**row))
        await self.session.commit()
        return LeadImportResult(
            created_rows=len(valid),
            skipped_duplicate_rows=len(duplicate_issues),
            skipped_invalid_rows=len(parsing_issues),
        )

    async def _split_import_rows(
        self,
        rows: list[tuple[int, dict]],
    ) -> tuple[list[dict], list[LeadImportIssue]]:
        existing = await self._existing_contacts(row for _, row in rows)
        seen_contacts: set[tuple[str, str]] = set()
        valid: list[dict] = []
        issues: list[LeadImportIssue] = []
        for row_number, row in rows:
            contacts = self._contact_keys(row["email"], row["phone"])
            if contacts.intersection(existing) or contacts.intersection(seen_contacts):
                issues.append(LeadImportIssue(row=row_number, message="Duplicate email or phone."))
                continue
            seen_contacts.update(contacts)
            valid.append(row)
        return valid, issues

    async def _existing_contacts(self, rows: Iterable[dict]) -> set[tuple[str, str]]:
        values = list(rows)
        emails = [row["email"] for row in values if row["email"]]
        phones = [row["phone"] for row in values if row["phone"]]
        clauses = []
        if emails:
            clauses.append(Lead.email.in_(emails))
        if phones:
            clauses.append(Lead.phone.in_(phones))
        if not clauses:
            return set()
        result = await self.session.execute(select(Lead.email, Lead.phone).where(or_(*clauses)))
        contacts: set[tuple[str, str]] = set()
        for email, phone in result:
            contacts.update(self._contact_keys(email, phone))
        return contacts

    async def _ensure_not_duplicate(
        self,
        email: str | None,
        phone: str | None,
        *,
        exclude_id: UUID | None = None,
    ) -> None:
        clauses = []
        if email:
            clauses.append(Lead.email == email)
        if phone:
            clauses.append(Lead.phone == phone)
        if not clauses:
            return
        statement = select(Lead.id).where(or_(*clauses))
        if exclude_id is not None:
            statement = statement.where(Lead.id != exclude_id)
        if await self.session.scalar(statement):
            raise ConflictError("A lead with this email or phone already exists")

    async def _read_import_rows(
        self, file: UploadFile
    ) -> tuple[list[tuple[int, dict]], list[LeadImportIssue]]:
        filename = file.filename or ""
        extension = Path(filename).suffix.lower()
        if extension not in {".xlsx", ".csv"}:
            raise BadRequestError("Upload an XLSX or CSV file")
        content = await file.read()
        if not content:
            raise BadRequestError("The import file is empty")
        raw_rows = self._read_xlsx(content) if extension == ".xlsx" else self._read_csv(content)
        if not raw_rows:
            raise BadRequestError("The import file has no rows")
        headers = self._map_headers(raw_rows[0])
        parsed: list[tuple[int, dict]] = []
        issues: list[LeadImportIssue] = []
        for row_number, raw_row in enumerate(raw_rows[1:], start=2):
            if not any(value not in (None, "") for value in raw_row):
                continue
            try:
                row = self._normalize_import_row(raw_row, headers)
                parsed.append((row_number, row))
            except (ValidationError, BadRequestError) as error:
                message = (
                    error.detail if isinstance(error, BadRequestError) else error.errors()[0]["msg"]
                )
                issues.append(LeadImportIssue(row=row_number, message=message))
        return parsed, issues

    @staticmethod
    def _read_xlsx(content: bytes) -> list[list[object]]:
        try:
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as error:
            raise BadRequestError("The XLSX file could not be read") from error
        worksheet = workbook.active
        return [list(row) for row in worksheet.iter_rows(values_only=True)]

    @staticmethod
    def _read_csv(content: bytes) -> list[list[object]]:
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise BadRequestError("CSV files must use UTF-8 encoding") from error
        return list(csv.reader(io.StringIO(decoded)))

    @staticmethod
    def _map_headers(headers: list[object]) -> dict[str, int]:
        aliases = {
            "full_name": {"full_name", "fullname", "name"},
            "email": {"email", "email_address", "emailaddress"},
            "phone": {
                "phone",
                "phone_number",
                "phonenumber",
                "mobile",
                "mobile_number",
                "mobilenumber",
            },
            "source": {"source"},
            "status": {"status"},
        }
        normalized = {
            LeadService._normalize_header(value): index
            for index, value in enumerate(headers)
            if value is not None
        }
        mapping: dict[str, int] = {}
        for field, accepted in aliases.items():
            index = next((normalized[name] for name in accepted if name in normalized), None)
            if index is not None:
                mapping[field] = index
        if "full_name" not in mapping:
            raise BadRequestError("A Full Name column is required")
        return mapping

    def _normalize_import_row(self, raw_row: list[object], headers: dict[str, int]) -> dict:
        raw = {field: self._row_value(raw_row, index) for field, index in headers.items()}
        status_value = raw.get("status", "")
        status = LeadStatus.NEW if not status_value else self._parse_status(status_value)
        lead = LeadCreate(
            full_name=raw.get("full_name", ""),
            email=raw.get("email") or None,
            phone=raw.get("phone") or None,
            source=raw.get("source") or None,
            status=status,
        )
        values = self._normalize_values(lead.model_dump())
        self._ensure_contact(values)
        return values

    @staticmethod
    def _normalize_values(values: dict) -> dict:
        normalized = dict(values)
        if "full_name" in normalized and normalized["full_name"] is not None:
            normalized["full_name"] = str(normalized["full_name"]).strip()
        if "email" in normalized and normalized["email"] is not None:
            normalized["email"] = str(normalized["email"]).strip().lower() or None
        if "phone" in normalized and normalized["phone"] is not None:
            digits = "".join(
                character for character in str(normalized["phone"]) if character.isdigit()
            )
            normalized["phone"] = digits or None
        if "source" in normalized and normalized["source"] is not None:
            normalized["source"] = str(normalized["source"]).strip() or None
        return normalized

    @staticmethod
    def _ensure_contact(values: dict) -> None:
        if not values.get("full_name"):
            raise BadRequestError("Full name is required")
        if not values.get("email") and not values.get("phone"):
            raise BadRequestError("Add an email or phone number")

    @staticmethod
    def _contact_keys(email: str | None, phone: str | None) -> set[tuple[str, str]]:
        keys = set()
        if email:
            keys.add(("email", email))
        if phone:
            keys.add(("phone", phone))
        return keys

    @staticmethod
    def _normalize_header(value: object) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")

    @staticmethod
    def _row_value(row: list[object], index: int) -> str:
        return "" if index >= len(row) or row[index] is None else str(row[index]).strip()

    @staticmethod
    def _parse_status(value: str) -> LeadStatus:
        normalized = re.sub(r"[\s-]+", "_", value.strip().lower())
        try:
            return LeadStatus(normalized)
        except ValueError as error:
            raise BadRequestError(f"Invalid status: {value}") from error
