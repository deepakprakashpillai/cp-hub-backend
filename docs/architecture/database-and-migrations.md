# Database And Migrations

## Database

The backend uses PostgreSQL.

Local development database is provided through Docker Compose:

```txt
service: postgres
image: postgres:16-alpine
database: cp_hub
user: postgres
password: postgres
port: 5432
```

Connection string:

```txt
postgresql+asyncpg://postgres:postgres@localhost:5432/cp_hub
```

## Time Handling

The backend stores date/time values in UTC.

Current rules:

- Database connection sets PostgreSQL timezone to UTC.
- `created_at` and `updated_at` use timezone-aware timestamps.
- Availability slots use UTC datetimes.
- Availability rules use UTC times.
- Frontend handles local display and converts values before sending them to the backend.
- Batch schedule days use a UTC calendar date.
- Batch-day single-create requests use timezone-aware UTC timestamps.
- Batch-day bulk/default option templates use UTC times.
- No local timezone conversion is performed by batch-day services.

## SQLAlchemy

SQLAlchemy models describe the database tables in Python.

Core files:

- `app/db/base.py`
- `app/db/session.py`
- `app/db/models.py`

`app/db/models.py` imports all model classes so Alembic can discover metadata for migrations.

## Alembic

Alembic manages database schema changes.

Migration files live in:

```txt
alembic/versions/
```

Migration files should be committed to git.

Current migration chain:

```txt
20260719_0001 -> 20260719_0002 -> 20260719_0003 -> 20260719_0004 -> 20260719_0005 -> 20260719_0006 -> 20260719_0007 -> 20260719_0008 -> 20260720_0009 -> 20260720_0010 -> 20260721_0011 -> 20260721_0012 -> 20260721_0013 -> 20260721_0014 -> 20260722_0015 -> 20260722_0016 -> 20260723_0017 -> 20260724_0018 -> 20260725_0019 -> 20260725_0020 -> 20260725_0021 -> 20260726_0022 -> 20260726_0023 -> 20260726_0024 -> 20260726_0025 -> 20260726_0026 -> 20260727_0027 -> 20260727_0028 -> 20260729_0029
```

`20260726_0025_add_email_password_auth.py` adds nullable Argon2 password hashes and a reserved
external-provider subject to `users`, plus database-backed single-use password setup/reset tokens.
The raw tokens are never stored.

`20260726_0026_add_auth_token_timestamp_defaults.py` adds database timestamp defaults for password
and refresh tokens so direct auth writes receive required audit timestamps.

`20260727_0027_add_teacher_class_cancellation_event.py` adds `cancelled_by_teacher` to the booking
event enum for teacher-initiated batch-option cancellation audits.

`20260727_0028_create_notifications.py` creates the notification outbox, recipient-owned inbox,
and delivery-audit tables. Business mutations enqueue an outbox event in the same database
transaction; a separate worker submits it to Notify-Hub. Notify-Hub owns workflow rendering and
channel delivery, including in-app delivery. Its signed in-app webhook creates the CP Hub inbox
record used by the existing self-service notification APIs. The reminder command should be scheduled
once per minute, while the outbox processor can be run continuously or at a short interval.

`20260729_0029_add_notification_metadata.py` adds structured `metadata` to each CP Hub inbox
record. Notify-Hub returns this rendered-event context in its in-app webhook; clients must use the
raw ISO `starts_at` and `ends_at` values to format class times in the viewer's browser timezone,
rather than parsing the notification body.

Useful commands:

```bash
uv run alembic current
uv run alembic history
uv run alembic upgrade head
uv run alembic downgrade -1
```

## Current Migration Details

`20260719_0001_create_users_table.py`

- Creates `user_role` enum.
- Creates `users` table.
- Adds unique email index.

`20260719_0002_create_teachers_table.py`

- Creates `teachers` table.
- Links teachers to users.
- Adds unique `user_id` index.

`20260719_0003_create_teacher_availability.py`

- Creates availability enums.
- Creates `teacher_availability_rules`.
- Creates `teacher_availability_slots`.

`20260719_0004_add_active_slot_unique_index.py`

- Adds a partial unique index for non-cancelled teacher slots:

```txt
teacher_id + starts_at + ends_at
where status <> cancelled
```

This prevents exact duplicate active slots while still allowing a cancelled slot time to be recreated later.

`20260719_0005_create_students_table.py`

- Creates `student_program_type` enum.
- Creates `student_status` enum.
- Creates `students` table.
- Links students to users.
- Adds unique `user_id` index.

`20260719_0006_create_packages_table.py`

- Creates `packages` table.
- Adds positive duration check.
- Adds non-negative price check.

`20260719_0007_create_student_payments_table.py`

- Creates `payment_method` enum.
- Creates `student_payments` table.
- Links payments to students.
- Optionally links payments to packages and users.
- Adds non-negative amount check.

`20260719_0008_create_student_access_grants_table.py`

- Creates `student_access_grant_type` enum.
- Creates `student_access_grants` table.
- Links access grants to students.
- Optionally links access grants to packages and users.
- Adds positive duration check.
- Adds valid access window check.

`20260720_0009_create_student_program_changes_table.py`

- Creates `student_program_changes` table.
- Links program changes to students.
- Optionally links program changes to users.
- Reuses `student_program_type` enum.
- Adds check that old and new program types differ.

`20260720_0010_create_class_sessions_and_bookings.py`

- Creates `batch_slot` enum.
- Creates `class_session_status` enum.
- Creates `booking_status` enum.
- Creates `class_sessions` table.
- Creates `bookings` table.
- Reuses `student_program_type` enum.
- Links class sessions to teachers and optional teacher availability slots.
- Links bookings to students and class sessions.
- Adds class session time range and capacity checks.
- Adds class session shape check for one-on-one versus batch sessions.
- Adds partial unique index for non-cancelled one-on-one sessions per teacher availability slot.
- Adds partial unique index for non-cancelled bookings per student and class session.

`20260721_0011_create_batch_groups.py`

- Creates `batch_groups` table.
- Creates `student_batch_memberships` table.
- Adds `batch_group_id` to `class_sessions`.
- Adds positive default capacity check for batch groups.
- Adds active membership end-state check.
- Adds partial unique index for active batch group names.
- Adds partial unique index so a student has only one active batch membership.
- Updates class session shape check so batch sessions require a batch group.
- Adds exclusion constraint preventing overlapping non-cancelled sessions in the same batch group.
- Enables PostgreSQL `btree_gist` extension for the batch overlap exclusion constraint.

`20260721_0012_create_booking_events.py`

- Creates `booking_event_type` enum.
- Creates `booking_events` table.
- Links booking events to bookings.
- Optionally links booking events to users as actors.
- Stores non-null cancellation/reschedule reasons.
- Stores optional event metadata as JSONB.

`20260721_0013_add_attendance_marked_booking_event.py`

- Adds `attendance_marked` value to `booking_event_type`.

`20260721_0014_add_manual_add_booking_event.py`

- Adds `manually_added_by_admin` value to `booking_event_type`.

`20260722_0015_add_admin_search_indexes.py`

- Enables PostgreSQL `pg_trgm`.
- Adds trigram GIN indexes for admin text search:
  - `users.full_name`
  - `users.email`
  - `users.phone`
  - `teachers.display_name`
- Adds btree indexes for admin list filters:
  - `students.status`
  - `students.program_type`
  - `students.access_starts_at`
  - `students.access_ends_at`
  - `teachers.is_active`

`20260722_0016_add_admin_class_booking_filter_indexes.py`

- Adds btree indexes for admin class and booking filters:
  - `class_sessions.status`
  - `bookings.status`
  - `bookings.booked_at`

`20260723_0017_add_student_assigned_teacher.py`

- Adds nullable `students.assigned_teacher_id`.
- Links permanent assignments to `teachers.id` with `ON DELETE SET NULL`.
- Adds an index for assigned-teacher lookups.
- Adds a database check preventing batch students from having an assigned teacher.

`20260724_0018_create_booking_notes.py`

- Creates the `booking_note_visibility` enum.
- Creates `booking_notes` with booking, class session, student, and teacher references.
- Adds indexes for booking, class session, student, and teacher note lookups.

`20260725_0019_add_batch_schedule_days.py`

- Creates `batch_schedule_days` with one stable parent per batch group and UTC date.
- Creates singleton `batch_schedule_defaults` and seeds three UTC option templates.
- Adds `batch_schedule_day_id`, `display_label`, and `option_order` to class sessions.
- Backfills existing batch sessions into UTC schedule-day parents.
- Keeps legacy `batch_slot` values while allowing custom display labels for new options.
- Adds booking event values for student selection and admin assignment/move/removal.

`20260725_0020_add_batch_day_cancellation.py`

- Adds schedule-day lifecycle and cancellation audit fields.
- Creates batch schedule-day audit events.
- Adds the per-booking batch-day cancellation event.

`20260725_0021_link_batch_groups_to_packages.py`

- Adds nullable `batch_groups.package_id` for backward-compatible migration.
- Links batch groups to packages with `ON DELETE SET NULL`.
- Adds the package lookup index.

`20260726_0022_create_leads.py`

- Creates the lead lifecycle enum and `leads` table.
- Adds indexes for normalized email, phone, and status list/filter lookups.

`20260726_0023_add_student_payment_ledger_indexes.py`

- Adds payment-date and payment-method indexes for the admin Finance ledger.

`20260726_0024_add_lead_conversion_link.py`

- Adds the optional, unique lead-to-student conversion link and conversion timestamp.

## Important Git Rules

Commit:

- `alembic/versions/*.py`
- `uv.lock`
- `.python-version`
- `.env.example`
- docs

Do not commit:

- `.env`
- `.venv/`
- `__pycache__/`
- `.pytest_cache/`
- `.ruff_cache/`
- local logs
