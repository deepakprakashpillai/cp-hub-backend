# Lead Management Domain

## Status

Implemented as a compact lead tracker for `/leads` and `/admin/leads`.

## Known Product Direction

The lead management portal will handle potential students before enrollment.

## Existing Enum

Lead status values already exist in shared enums:

- `new`
- `contacted`
- `trial_booked`
- `enrolled`
- `lost`

## Model And Rules

- `leads` stores full name, optional email, optional phone, optional free-text source, status,
  optional converted-student link, and UTC timestamps.
- A lead requires a full name and at least one contact method.
- Email is normalized to lowercase and phone to digits before duplicate checks and storage.
- Matching email or phone identifies a duplicate. The current status can move freely between all five values.
- Deletion is permanent. There is no archive, assignment, note, reminder, or status-history flow.

## APIs

- `GET /api/v1/leads` supports `q`, `status`, `page`, and `page_size`.
- `GET /api/v1/leads/summary` returns total and per-status counts for the workspace summary strip.
- `POST /api/v1/leads`, `PATCH /api/v1/leads/{lead_id}`, and `DELETE /api/v1/leads/{lead_id}` manage individual leads.
- `POST /api/v1/leads/import/preview` and `POST /api/v1/leads/import` accept XLSX or UTF-8 CSV files. The first worksheet is read for XLSX.
- Import accepts Full Name, Email, Phone, Source, and Status headers in readable or snake-case form. Blank status defaults to `new`; invalid and duplicate rows are reported/skipped.

## Local Seed Data

Run `uv run seed-leads` to create 20 idempotent example leads with balanced status and source data.
## Admin Lead Conversion

`POST /api/v1/admin/leads/{lead_id}/convert` converts one enrolled lead into an enrolled student.

The multi-entity conversion is owned by `LeadConversionWorkflow`; the lead, user, and student
changes commit atomically.

- The request confirms a required email and selects `one_on_one` or `batch` program type.
- Creation of the student user, student profile, and lead-to-student link is atomic.
- A lead can be converted only once; the stored `converted_student_id` and `converted_at` preserve
  the link.
- Conversion does not create payments, grant access, or assign a batch/teacher.
