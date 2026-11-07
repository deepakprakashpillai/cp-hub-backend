# Project Status

Last updated: 2026-07-29

## Current Stack

- FastAPI
- PostgreSQL
- SQLAlchemy async ORM
- Alembic migrations
- Pydantic v2
- uv
- Docker Compose for local Postgres
- pytest
- ruff

## Implemented

- Project scaffold with modular backend structure.
- Local PostgreSQL setup through Docker Compose.
- Alembic migration setup.
- UTC-aware database connection.
- Users domain.
- Teacher profile domain.
- Teacher availability rules and slots.
- Manual availability slots.
- Manual blocked time.
- Bulk manual slot creation.
- Teacher slot generation service.
- Standalone slot generation command.
- Student profile domain foundation.
- Packages domain foundation.
- Student payment records.
- Student access grants.
- Student program switch history.
- Classes and bookings foundation.
- One-on-one booking from teacher availability slots.
- Batch class session creation and batch booking.
- Future booking cancellation on student program switch.
- Batch groups.
- Student batch membership and transfer history.
- Bulk batch session generation.
- Batch group-aware booking restrictions.
- Booking event logs.
- Teacher-authored booking feedback notes with admin visibility.
- Student and admin booking cancellation.
- Student and admin booking rescheduling.
- Attendance marking and correction.
- Class auto-completion after attendance is fully marked.
- Admin manual-add override for class sessions.
- Admin orchestration endpoints for teacher and student creation.
- Admin student lifecycle aliases for payments, access grants, program switching, and batch group
  assignment.
- Admin class and booking operation aliases for batch session generation, batch class creation,
  manual add, attendance, cancellation, and rescheduling.
- Admin read aliases for students, teachers, classes, bookings, batch groups, and packages.
- Paginated list responses for existing and admin list endpoints.
- Admin dashboard summary endpoint for aggregate student, teacher, batch group, class, booking,
  and payment counts.
- Admin student and teacher search/filter support.
- Permanent active-teacher assignments for one-on-one students.
- Database indexes for scalable admin student and teacher search/filter lists.
- Admin class and booking filters for schedule and attendance operations.
- Database indexes for scalable admin class and booking filters.
- Admin profile update endpoints for students, teachers, and packages.
- Admin user/account update endpoint for base user fields.
- Admin void/delete aliases for packages, batch groups, and student payments.
- Admin teacher scheduling aliases for availability rules, slots, blocks, bulk slots, and slot
  generation.
- Admin class cancellation that cancels active bookings and reopens future one-on-one teacher
  slots.
- Admin class projections, searchable schedule listing, and paginated roster reads.
- Admin class activity timeline with aggregated booking events and actor/student identity.
- Admin batch-group and package search, filtering, deterministic sorting, and aggregate group
  counts.
- Admin create aliases for one-on-one bookings, batch groups, batch memberships, and packages.
- Atomic batch membership removal with future group-booking cancellation.
- Admin whole-class one-on-one and batch rescheduling.
- UTC batch schedule-day grouping with configurable session-option labels and up to eight options.
- Persistent UTC batch scheduling defaults seeded with Morning, Noon, and Evening.
- Atomic single-day and weekday/range batch-day generation.
- Student batch-day option discovery and one-option selection.
- Admin batch-day student assignment, movement, removal, and option editing.
- Atomic single-day and bulk batch schedule-day cancellation with audit events.
- Batch-group package linkage and package-aware membership validation with explicit admin override.
- Local debug CORS support for the Vite frontend on `127.0.0.1:5173` / `localhost:5173`.
- Lead management CRUD, status filtering, permanent deletion, and XLSX/CSV import preview/confirmation.
- Email/password authentication foundation: Argon2 passwords, 15-minute JWT access tokens,
  HttpOnly rotating refresh cookies, password setup/reset tokens, `/auth/login`, `/auth/refresh`,
  `/auth/logout`, and `/auth/me`.
- Admin teacher creation issues a single-use password setup invitation; Resend delivery is enabled by configuration and local development logs the link instead.
- Authenticated self-service teacher and student portal APIs. Teacher routes are scoped to the
  authenticated teacher's profile, assigned classes, roster, attendance, availability, students,
  and booking notes. Student routes are scoped to the authenticated student's profile, grants,
  bookings, slots, batch-day choices, and student-visible feedback.
- Teacher self-service rescheduling and cancellation for assigned future batch-day options, with
  per-booking teacher audit events.
- Durable notification outbox dispatch to Notify-Hub, signed Notify-Hub in-app delivery webhooks,
  and self-scoped notification inbox APIs. Notify-Hub owns workflow rendering and channel delivery;
  CP Hub stores structured notification metadata for rich client-side rendering and browser-local
  class times.
- Notification producers for booking lifecycle, attendance, student-visible feedback, access grants,
  payments, program/status/teacher-assignment changes, teacher deactivation, and account changes.
- Notification worker and scheduled reminder commands for 1-hour class and access-expiry reminders.

## Current Migration Head

```txt
20260729_0029
```

Migrations:

- `20260719_0001_create_users_table.py`
- `20260719_0002_create_teachers_table.py`
- `20260719_0003_create_teacher_availability.py`
- `20260719_0004_add_active_slot_unique_index.py`
- `20260719_0005_create_students_table.py`
- `20260719_0006_create_packages_table.py`
- `20260719_0007_create_student_payments_table.py`
- `20260719_0008_create_student_access_grants_table.py`
- `20260720_0009_create_student_program_changes_table.py`
- `20260720_0010_create_class_sessions_and_bookings.py`
- `20260721_0011_create_batch_groups.py`
- `20260721_0012_create_booking_events.py`
- `20260721_0013_add_attendance_marked_booking_event.py`
- `20260721_0014_add_manual_add_booking_event.py`
- `20260722_0015_add_admin_search_indexes.py`
- `20260722_0016_add_admin_class_booking_filter_indexes.py`
- `20260723_0017_add_student_assigned_teacher.py`
- `20260724_0018_create_booking_notes.py`
- `20260725_0019_add_batch_schedule_days.py`
- `20260725_0020_add_batch_day_cancellation.py`
- `20260725_0021_link_batch_groups_to_packages.py`
- `20260726_0022_create_leads.py`
- `20260726_0023_add_student_payment_ledger_indexes.py`
- `20260726_0024_add_lead_conversion_link.py`
- `20260726_0025_add_email_password_auth.py`
- `20260726_0026_add_auth_token_timestamp_defaults.py`
- `20260727_0027_add_teacher_class_cancellation_event.py`
- `20260727_0028_create_notifications.py`
- `20260729_0029_add_notification_metadata.py`

## Current Commands

Run app locally:

```bash
uv run uvicorn app.main:app --reload
```

Run tests:

```bash
uv run pytest
```

Run lint:

```bash
uv run ruff check .
```

Apply migrations:

```bash
uv run alembic upgrade head
```

Generate teacher slots:

```bash
uv run generate-teacher-slots
```

Process durable notifications:

```bash
uv run process-notifications
uv run run-notification-reminders
```

Notify-Hub configuration:

```txt
NOTIFY_HUB_BASE_URL=https://notify-hub.example
NOTIFY_HUB_API_KEY={environment-id}.{secret}
NOTIFY_HUB_WEBHOOK_SECRET={environment webhook secret}
```

Notify-Hub must be configured with the CP Hub in-app webhook URL:

```txt
POST {CP_HUB_API_URL}/api/v1/notifications/in-app-deliveries
```

The in-app webhook `content.data` is persisted as notification `metadata`. For class notifications
it includes `class_id`, `booking_id`, `teacher_name`, `student_name`, `starts_at`, and `ends_at`.
Frontend clients should render those fields directly and localise the ISO timestamps in the browser.

## Domain Docs

- [Users](domains/users.md)
- [Admin](domains/admin.md)
- [Teacher](domains/teacher.md)
- [Students](domains/students.md)
- [Classes And Bookings](domains/classes-and-bookings.md)
- [Lead Management](domains/lead-management.md)

## Architecture Docs

- [Database And Migrations](architecture/database-and-migrations.md)
- [Module Boundaries](architecture/module-boundaries.md)

## Next Recommended Domain

Complete browser-level role-portal QA against the frontend cutover.
