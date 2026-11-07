# Admin Domain

## Status

Admin adapters and focused read/workflow services implemented.

Implemented files:

- `app/modules/admin/schemas.py`
- `app/modules/admin/routes.py`
- `app/modules/admin/http/`
- `app/modules/read_models/`

## Purpose

The admin domain provides authenticated, role-protected frontend adapters for admin actions. Its
router aggregates feature routers for dashboard, accounts, finance, scheduling, classes/bookings,
leads, and catalog/batch management under the unchanged `/api/v1/admin` prefix.

Admin endpoints call the owning feature service directly for leaf operations. Presentation joins
use focused query services in `app/modules/read_models/`; multi-entity onboarding and other
cross-feature mutations use explicit workflow services. There is no `AdminService` compatibility
façade.

## Pagination

List endpoints accept:

- `page`, default `1`, minimum `1`
- `page_size`, default `25`, minimum `1`, maximum `100`

Paginated response shape:

```txt
{
  "items": [...],
  "total": 0,
  "page": 1,
  "page_size": 25
}
```

## Implemented Workflows

### Admin Reads

Endpoints:

```txt
GET /api/v1/admin/dashboard/summary
PATCH /api/v1/admin/users/{user_id}
GET /api/v1/admin/students
GET /api/v1/admin/students/{student_id}
PATCH /api/v1/admin/students/{student_id}
GET /api/v1/admin/teachers
GET /api/v1/admin/teachers/{teacher_id}
PATCH /api/v1/admin/teachers/{teacher_id}
POST /api/v1/admin/teachers/{teacher_id}/availability/generate
GET /api/v1/admin/teacher-availability/rules
POST /api/v1/admin/teacher-availability/rules
GET /api/v1/admin/teacher-availability/rules/{rule_id}
PATCH /api/v1/admin/teacher-availability/rules/{rule_id}
DELETE /api/v1/admin/teacher-availability/rules/{rule_id}
GET /api/v1/admin/teacher-availability/slots
POST /api/v1/admin/teacher-availability/slots
POST /api/v1/admin/teacher-availability/slots/bulk
POST /api/v1/admin/teacher-availability/blocks
GET /api/v1/admin/teacher-availability/slots/{slot_id}
PATCH /api/v1/admin/teacher-availability/slots/{slot_id}
DELETE /api/v1/admin/teacher-availability/slots/{slot_id}
GET /api/v1/admin/classes
GET /api/v1/admin/classes/{class_session_id}
GET /api/v1/admin/classes/{class_session_id}/roster
GET /api/v1/admin/classes/{class_session_id}/activity
POST /api/v1/admin/classes/{class_session_id}/cancel
POST /api/v1/admin/classes/{class_session_id}/reschedule/one-on-one
POST /api/v1/admin/classes/{class_session_id}/reschedule/batch
GET /api/v1/admin/bookings
POST /api/v1/admin/bookings/one-on-one
GET /api/v1/admin/bookings/{booking_id}
GET /api/v1/admin/bookings/{booking_id}/events
GET /api/v1/admin/bookings/{booking_id}/notes
GET /api/v1/admin/batch-groups
POST /api/v1/admin/batch-groups
GET /api/v1/admin/batch-groups/{batch_group_id}
PATCH /api/v1/admin/batch-groups/{batch_group_id}
POST /api/v1/admin/batch-groups/{batch_group_id}/void
GET /api/v1/admin/batch-groups/{batch_group_id}/students
POST /api/v1/admin/batch-groups/{batch_group_id}/students
DELETE /api/v1/admin/batch-groups/{batch_group_id}/students/{student_id}
GET /api/v1/admin/packages
POST /api/v1/admin/packages
GET /api/v1/admin/packages/{package_id}
PATCH /api/v1/admin/packages/{package_id}
POST /api/v1/admin/packages/{package_id}/void
GET /api/v1/admin/batch-schedule-defaults
PATCH /api/v1/admin/batch-schedule-defaults
GET /api/v1/admin/batch-schedule-days
POST /api/v1/admin/batch-schedule-days
POST /api/v1/admin/batch-schedule-days/bulk
GET /api/v1/admin/batch-schedule-days/{day_id}
POST /api/v1/admin/batch-schedule-days/{day_id}/options
PATCH /api/v1/admin/batch-schedule-days/{day_id}/options/{class_session_id}
DELETE /api/v1/admin/batch-schedule-days/{day_id}/options/{class_session_id}
PUT /api/v1/admin/batch-schedule-days/{day_id}/students/{student_id}
DELETE /api/v1/admin/batch-schedule-days/{day_id}/students/{student_id}
```

Rules:

- Student and teacher admin reads return nested `user` data with the profile record.
- The admin student list supports `sort_by` values `created_at`, `joined_at`, `name`, `status`,
  `program_type`, and `access_ends_at`, plus `sort_order` values `asc` and `desc`.
- Admin student sorting defaults to newest `created_at` first, happens before pagination, and puts
  null sort values last in either direction.
- Admin class reads preserve every existing class-session field and add compact `teacher`,
  `batch_group`, `primary_student`, and `booking_counts` projections.
- `booking_counts` contains `booked`, `cancelled`, `attended`, and `missed`.
- Admin class projection queries load summaries and counts in the paginated query rather than
  issuing per-class lookups.
- Admin student list supports `q`, `status`, `program_type`, `access_state`, `batch_group_id`, and
  permanent `assigned_teacher_id`.
- Admin teacher list supports `q`, teacher-profile `is_active`, linked-account
  `account_is_active`, `sort_by`, and `sort_order`.
- Admin class list supports `q`, `program_type`, `starts_from`, `starts_to`, `status`,
  `teacher_id`, `batch_group_id`, and `sort_order`.
- Admin booking list supports `student_id`, `class_session_id`, `status`, `teacher_id`,
  `starts_from`, and `starts_to`.
- Admin batch group list supports `q`, `is_active`, `sort_by`, and `sort_order`.
- Admin package list supports `q`, `is_active`, `sort_by`, and `sort_order`.
- Admin batch group student list supports `is_active`.

Admin student search/filter rules:

- `q` searches linked user `full_name`, `email`, and `phone`.
- `status` filters by student status.
- `program_type` filters by `one_on_one` or `batch`.
- `access_state` values are `valid`, `expired`, `not_started`, and `none`.
- `access_state` is based on the raw access window. Combine it with `status=active` when an
  active-only access view is needed.
- `batch_group_id` filters students by active membership in that batch group.
- `assigned_teacher_id` matches `students.assigned_teacher_id` directly. It does not infer
  assignment from historical class attendance.

Admin teacher search/filter rules:

- `q` searches teacher `display_name` plus linked user `full_name`, `email`, and `phone`.
- `is_active` filters by teacher profile active state.
- `account_is_active` independently filters linked `users.is_active`.
- `sort_by` values are `created_at`, `name`, `display_name`, and `is_active`.
- `name` sorts by linked `users.full_name`; `display_name` sorts by
  `teachers.display_name`.
- Teacher sorting defaults to `created_at desc` and uses teacher ID as a deterministic
  secondary sort.

Admin class filter rules:

- `q` searches assigned teacher full/display name, batch-group name, and the full name, email, or
  phone of students with non-cancelled roster bookings.
- `program_type` filters by `one_on_one` or `batch`.
- `starts_from` and `starts_to` filter by `class_sessions.starts_at`.
- `status` filters by class session status.
- `teacher_id` filters by assigned teacher.
- `batch_group_id` filters by batch group.
- `sort_order` controls `class_sessions.starts_at` ordering and defaults to `asc`.
- Class-session ID is used as a deterministic secondary sort.

Admin batch-group list rules:

- Responses add `active_member_count` and `upcoming_scheduled_count`.
- `active_member_count` counts active membership rows.
- `upcoming_scheduled_count` counts scheduled sessions whose start is later than query time.
- `q` searches batch-group name.
- `sort_by` supports `created_at`, `name`, `active_member_count`,
  `upcoming_scheduled_count`, and `is_active`.
- Sorting defaults to `created_at desc` and uses batch-group ID as a deterministic secondary sort.

Admin package list rules:

- `q` searches package name and `is_active` filters package status.
- `sort_by` supports `created_at`, `name`, `duration_days`, `price_amount`, and `is_active`.
- Sorting defaults to `created_at desc` and uses package ID as a deterministic secondary sort.

Admin booking filter rules:

- `student_id` filters by booking student.
- `class_session_id` filters by exact class session.
- `status` filters by booking status.
- `teacher_id` filters through the linked class session teacher.
- `starts_from` and `starts_to` filter by linked `class_sessions.starts_at`, not booking creation
  time.

### Admin Profile And Account Updates

Endpoints:

```txt
PATCH /api/v1/admin/students/{student_id}
PATCH /api/v1/admin/teachers/{teacher_id}
PATCH /api/v1/admin/packages/{package_id}
PATCH /api/v1/admin/users/{user_id}
```

Rules:

- Student profile updates reuse the existing student update validation.
- Student `program_type` changes through the admin patch use the existing student program switch
  behavior so history, future booking cancellation, and batch membership cleanup still happen.
- Teacher profile updates can change `display_name`, `bio`, `profile_photo_url`, and `is_active`.
- Package updates reuse the existing package update behavior and can change `name`,
  `duration_days`, `price_amount`, `currency`, and `is_active`.
- User/account updates can change `full_name`, `email`, `phone`, and `is_active`.
- User/account updates cannot change `role`.
- User email updates enforce the existing unique email rule.
- Auth and role-based permissions are still deferred.
- Availability slot listing supports `status`, `source`, and `sort_order` in addition to
  `teacher_id`, `starts_from`, and `starts_to`.
- Slot ordering uses `starts_at`, defaults to `asc`, and uses slot ID as a deterministic
  secondary sort.

### Admin Void And Delete Aliases

Endpoints:

```txt
POST /api/v1/admin/packages/{package_id}/void
PATCH /api/v1/admin/batch-groups/{batch_group_id}
POST /api/v1/admin/batch-groups/{batch_group_id}/void
PATCH /api/v1/admin/students/{student_id}/payments/{payment_id}
DELETE /api/v1/admin/students/{student_id}/payments/{payment_id}
```

Rules:

- Package void reuses the existing package void behavior and sets `is_active = false`.
- Batch group update and void reuse existing batch group behavior.
- Voiding a batch group cancels future scheduled sessions and future booked bookings for that
  group through existing domain behavior.
- Admin payment update/delete aliases are path-scoped by student.
- A path-scoped admin payment update/delete only works when the payment already belongs to the
  path `student_id`; the endpoint does not move payments between students.

### Finance Payment Ledger

Endpoints:

```txt
GET /api/v1/admin/payments
GET /api/v1/admin/payments/summary
POST /api/v1/admin/payments
PATCH /api/v1/admin/payments/{payment_id}
DELETE /api/v1/admin/payments/{payment_id}
```

Rules:

- Ledger reads project payment records with student identity and optional package summaries.
- List and summary accept `q`, `payment_method`, `package_id`, `currency`, `paid_from`, and
  exclusive `paid_to`; list additionally supports `paid_at`/`amount_paid` sorting and pagination.
- Summary groups totals by currency before method breakdown, so currencies are never combined.
- Global create chooses the student once. Global update cannot move a payment to another student.
- Payment records do not change student status or access. Delete remains permanent.

### Admin Teacher Scheduling

Endpoints:

```txt
GET /api/v1/admin/teacher-availability/rules
POST /api/v1/admin/teacher-availability/rules
GET /api/v1/admin/teacher-availability/rules/{rule_id}
PATCH /api/v1/admin/teacher-availability/rules/{rule_id}
DELETE /api/v1/admin/teacher-availability/rules/{rule_id}
GET /api/v1/admin/teacher-availability/slots
POST /api/v1/admin/teacher-availability/slots
POST /api/v1/admin/teacher-availability/slots/bulk
POST /api/v1/admin/teacher-availability/blocks
GET /api/v1/admin/teacher-availability/slots/{slot_id}
PATCH /api/v1/admin/teacher-availability/slots/{slot_id}
DELETE /api/v1/admin/teacher-availability/slots/{slot_id}
POST /api/v1/admin/teachers/{teacher_id}/availability/generate
```

Rules:

- Admin teacher scheduling endpoints are aliases over the existing schedule services.
- Availability rule create/update/delete still triggers slot sync through existing behavior.
- Booked slots still cannot be edited or deleted.
- Slot generation for a teacher returns `rules_checked`, `slots_created`, `slots_cancelled`, and
  `slots_skipped`.
- Slot generation accepts `days_ahead`, default `14`, minimum `1`, maximum `90`.
- Auth and role-based permissions are still deferred.

### Admin Dashboard Summary

Endpoint:

```txt
GET /api/v1/admin/dashboard/summary
```

Query params:

- `starts_from`, optional UTC datetime.
- `starts_to`, optional UTC datetime.

Rules:

- The dashboard endpoint returns aggregate counters only; it is not paginated.
- If both query params are omitted, the backend uses the current UTC day.
- If `starts_to` is omitted, it defaults to one day after `starts_from`.
- `starts_from` must be before `starts_to`.
- Date-windowed class counts use `class_sessions.starts_at`.
- Date-windowed booking counts use `bookings.booked_at`.
- Date-windowed payment counts use `student_payments.paid_at`.
- Payment totals are returned as integer minor units.
- `expired_access` counts active students whose `access_ends_at` is less than or equal to the
  summary generation time.
- `active_with_valid_access` counts active students whose access window contains the summary
  generation time.
- `action_items` returns current operational follow-up counts: active students with no complete
  access window, active students with expired access, enrolled unconverted leads, and scheduled
  sessions that have already started.

Response shape:

```txt
{
  "window": {
    "starts_from": datetime,
    "starts_to": datetime,
    "generated_at": datetime
  },
  "students": {
    "total": int,
    "active": int,
    "enrolled": int,
    "paused": int,
    "completed": int,
    "cancelled": int,
    "active_with_valid_access": int,
    "expired_access": int
  },
  "teachers": {
    "total": int,
    "active": int,
    "inactive": int
  },
  "batch_groups": {
    "total": int,
    "active": int,
    "inactive": int
  },
  "classes": {
    "scheduled": int,
    "completed": int,
    "cancelled": int
  },
  "bookings": {
    "booked": int,
    "cancelled": int,
    "attended": int,
    "missed": int
  },
  "payments": {
    "count": int,
    "total_amount_paid": int
  }
}
```

### Create Teacher

Endpoint:

```txt
POST /api/v1/admin/teachers
```

Creates:

- A `users` row with `role = teacher`.
- A linked `teachers` profile.

Rules:

- Creation is atomic; if teacher profile creation fails, the user is not committed.
- `users.is_active` can be provided and defaults to `true`.
- `teachers.is_active` uses the existing teacher profile default.
- No auth, password, invite, or permission checks are implemented.

Response shape:

```txt
{
  "user": UserRead,
  "teacher": TeacherRead
}
```

### Create Student

Endpoint:

```txt
POST /api/v1/admin/students
```

Creates:

- A `users` row with `role = student`.
- A linked `students` profile.

Rules:

- Creation is atomic; if student profile creation fails, the user is not committed.
- `users.is_active` can be provided and defaults to `true`.
- Payments, access grants, and batch assignment remain separate admin actions.
- No auth, password, invite, or permission checks are implemented.

Response shape:

```txt
{
  "user": UserRead,
  "student": StudentRead
}
```

### Student Payments

Endpoints:

```txt
GET /api/v1/admin/students/{student_id}/payments
POST /api/v1/admin/students/{student_id}/payments
```

Rules:

- These are path-scoped admin endpoints; `student_id` comes from the URL, not the request body.
- Payment creation reuses the existing student payment service.
- Payment records do not activate students and do not grant access.

### Student Access Grants

Endpoints:

```txt
GET /api/v1/admin/students/{student_id}/access-grants
POST /api/v1/admin/students/{student_id}/access-grants
```

Rules:

- These are path-scoped admin endpoints; `student_id` comes from the URL, not the request body.
- Access grant creation reuses the existing access grant service.
- Creating an access grant updates the student's access window through existing domain behavior.

### Student Program Switch

Endpoint:

```txt
POST /api/v1/admin/students/{student_id}/program-switch
```

Rules:

- Reuses the existing student program switch service.
- Future bookings are cancelled through existing domain behavior.
- Switching from `batch` to `one_on_one` ends the active batch membership through existing domain
  behavior.

### Student Batch Group

Endpoints:

```txt
GET /api/v1/admin/students/{student_id}/batch-memberships
POST /api/v1/admin/students/{student_id}/batch-group
```

Rules:

- `POST /batch-group` means admin sets the student's current batch group.
- The endpoint supports first assignment and transfer.
- Assignment and transfer require a currently active access grant for the destination batch
  group's linked package.
- `allow_package_access_override = true` bypasses that package match only and requires `reason`.
- Internally it reuses existing batch transfer behavior.
- When the student already has another active batch membership, future booked bookings from the
  old batch group are cancelled through existing domain behavior.
- Admin can also add a student through
  `POST /api/v1/admin/batch-groups/{batch_group_id}/students`.
- `DELETE /api/v1/admin/batch-groups/{batch_group_id}/students/{student_id}` accepts an optional
  `reason` query parameter, ends that exact active membership, cancels the student's future
  `booked` bookings for the group, and logs `cancelled_by_admin` events.
- Membership removal leaves `students.program_type = batch`, allowing a temporarily unassigned
  batch student.
- Membership end, booking cancellation, and event creation commit atomically.

Batch-group create, update, detail, and list responses expose `package_id` and a compact package
summary containing ID, name, duration, price, currency, and active state. New active groups require
an active package. Existing migrated groups may remain unlinked until configured. Package changes
do not modify existing student access or membership records.

### Batch Session Generation

Endpoint:

```txt
POST /api/v1/admin/batch-groups/{batch_group_id}/sessions/generate
```

Rules:

- Reuses the existing batch session generation service.
- The response includes `created_count` and the generated class sessions.
- Existing generation validation and overlap rules apply.
- Generated sessions are associated with one UTC `batch_schedule_day` parent per generated date.

### Batch Schedule Days

Batch schedule days group all selectable session options for one batch group and UTC date.

Defaults endpoints:

```txt
GET /api/v1/admin/batch-schedule-defaults
PATCH /api/v1/admin/batch-schedule-defaults
```

Defaults:

- `timezone` is returned as the fixed, read-only value `UTC`; it is not accepted by the
  defaults update request.
- Seeded labels/times are Morning at `08:00`, Noon at `12:00`, and Evening at `18:00`.
- Seeded duration is 60 minutes and default option count is 3.
- Admin can configure 1 to 8 validated templates.
- Capacity strategy is `batch_group_default` or `fixed`.
- A default teacher is optional and must be active when configured.

Scheduling endpoints:

```txt
GET /api/v1/admin/batch-schedule-days
POST /api/v1/admin/batch-schedule-days
POST /api/v1/admin/batch-schedule-days/bulk
POST /api/v1/admin/batch-schedule-days/cancel-bulk
GET /api/v1/admin/batch-schedule-days/{day_id}
POST /api/v1/admin/batch-schedule-days/{day_id}/cancel
```

Rules:

- There is exactly one batch schedule day per batch group and UTC date.
- Single-day creation accepts timezone-aware UTC `starts_at` and `ends_at` values.
- Omitting single-day options applies the persisted defaults.
- Bulk creation accepts a UTC date range, selected weekdays, and one reusable set of UTC-time
  option templates.
- Bulk scheduling creates an independent parent and option sessions for every selected date.
- Single and bulk creation are atomic.
- Options require unique display labels within the day and may use arbitrary labels.
- A shared default teacher can be overridden per option.
- Teachers must be active and cannot overlap another non-cancelled class.
- Options for the same batch cannot overlap existing sessions or each other.
- Conflict responses from bulk creation identify the failing UTC date.
- Day cancellation atomically marks every still-scheduled option cancelled and cancels every
  active booking in those options. Completed options remain unchanged.
- Cancellation preserves all parents, sessions, bookings, and audit events. It emits one
  day-level event and a `batch_day_cancelled` event for each affected booking.
- Repeated cancellation is idempotent. Wholly past or completed days return a conflict.
- Bulk cancellation validates and locks every requested day before mutation, so one invalid day
  rolls back the entire request.

Read projections include:

- Batch identity and UTC date.
- Day lifecycle/cancellation fields and ordered option sessions with status, nested teacher,
  capacity, active booking count, and remaining capacity. Cancelled options remain visible.
- Eligible active-student count.
- Compact students who have not selected an option.

Option-management endpoints:

```txt
POST /api/v1/admin/batch-schedule-days/{day_id}/options
PATCH /api/v1/admin/batch-schedule-days/{day_id}/options/{class_session_id}
DELETE /api/v1/admin/batch-schedule-days/{day_id}/options/{class_session_id}
```

- Admin can maintain up to eight active options.
- Options must remain on the parent's UTC date.
- Capacity cannot be reduced below active booking count.
- Time changes reject teacher, batch-group, and booked-student UTC-day conflicts.
- Removing an option is rejected while active students remain assigned.
- Removing an empty option marks its class session cancelled so history remains intact.

Student allocation endpoints:

```txt
PUT /api/v1/admin/batch-schedule-days/{day_id}/students/{student_id}
DELETE /api/v1/admin/batch-schedule-days/{day_id}/students/{student_id}
```

- Assignment enforces active batch membership, student status/access, scheduled state, UTC-day
  uniqueness, and option capacity.
- Assigning a student who selected another option in the same day atomically cancels the old
  booking and creates the replacement.
- Removal cancels the active day selection without cancelling the option class.
- Assignment, movement, and removal emit explicit booking events with actor, reason, source,
  batch-day ID, and old/new session metadata.

### Batch Class Creation

Endpoint:

```txt
POST /api/v1/admin/classes/batch
```

Rules:

- Reuses the existing batch class session creation service.
- Batch class validation and overlap rules apply.

### Add Student To Class

Endpoint:

```txt
POST /api/v1/admin/classes/{class_session_id}/students
```

Rules:

- Reuses the existing admin manual-add booking service.
- `class_session_id` comes from the URL.
- Admin manual-add override behavior remains defined by the bookings domain.

### Class Attendance

Endpoint:

```txt
POST /api/v1/admin/classes/{class_session_id}/attendance
```

Rules:

- Reuses the existing class attendance service.
- Attendance marking and class auto-completion behavior remain defined by the bookings domain.

### Booking Feedback

Endpoint:

```txt
GET /api/v1/admin/bookings/{booking_id}/notes
```

Rules:

- Admin can read every teacher-authored note for the booking.
- Results are paginated in creation order.
- Notes remain separate from booking event history and do not affect booking or class status.

### Booking Cancellation And Reschedule

Endpoints:

```txt
POST /api/v1/admin/bookings/{booking_id}/cancel
POST /api/v1/admin/bookings/{booking_id}/reschedule/one-on-one
POST /api/v1/admin/bookings/{booking_id}/reschedule/batch
```

Rules:

- Reuses the existing admin booking cancellation and reschedule services.
- Admin cancellation and reschedule behavior remain defined by the bookings domain.

Creation aliases:

```txt
POST /api/v1/admin/bookings/one-on-one
POST /api/v1/admin/batch-groups
POST /api/v1/admin/batch-groups/{batch_group_id}/students
POST /api/v1/admin/packages
```

These aliases reuse existing domain create schemas, validation, services, and response records.

### Class Projection, Roster, And Reschedule

Endpoints:

```txt
GET /api/v1/admin/classes/{class_session_id}/roster
GET /api/v1/admin/classes/{class_session_id}/activity
POST /api/v1/admin/classes/{class_session_id}/reschedule/one-on-one
POST /api/v1/admin/classes/{class_session_id}/reschedule/batch
```

Rules:

- The roster is paginated and returns each booking with compact nested student/user identity.
- The activity endpoint is paginated and aggregates booking events from every booking belonging
  to the class session.
- Activity rows include compact student identity, nullable nested actor identity, a human-readable
  actor label, reason, metadata, and event time without per-row user or student lookups.
- Actor labels use the actor's full name when present and `System` when `actor_user_id` is null.
- Activity is ordered newest first by `booking_events.created_at`, then event ID descending.
- Class cancellation and class reschedule actions appear through the booking events emitted for
  each affected booking. The response permits nullable booking/student fields for future
  class-only audit sources.
- One-on-one class reschedule locates the class's active booking and reuses the existing admin
  one-on-one booking-reschedule flow. It returns the replacement class and booking.
- Batch class reschedule updates the existing class and preserves its active booking IDs.
- Batch reschedule is limited to scheduled, not-yet-started classes and requires a future,
  timezone-aware valid time range.
- Omitted teacher, batch-slot, and capacity values preserve the current values. Explicit
  `teacher_id = null` clears the teacher; batch slot and capacity cannot be null.
- Batch reschedule rejects teacher or batch-group overlaps, capacity below the active booked
  roster size, and a booked student's existing non-cancelled class on the destination UTC day.
- Each preserved `booked` booking receives `rescheduled_from` and `rescheduled_to` events with
  old/new timing, teacher, slot, and capacity metadata.
- Batch class mutation and event creation commit atomically.

### Class Cancellation

Endpoint:

```txt
POST /api/v1/admin/classes/{class_session_id}/cancel
```

Rules:

- Admin can cancel scheduled class sessions directly.
- Completed class sessions cannot be cancelled.
- Already-cancelled class sessions cannot be cancelled again.
- Cancelling a class marks the class session `cancelled`.
- Cancelling a class marks all `booked` bookings for that class `cancelled`.
- Cancelling a class logs `cancelled_by_admin` booking events for each cancelled booking.
- For future one-on-one class sessions, cancellation reopens the linked teacher availability slot
  when that slot is still `booked`.
- Whole-class rescheduling is implemented through the program-specific admin endpoints.

## Design Rules

- Admin routes orchestrate existing domain services.
- Domain services remain the source of business rules and validation.
- Existing domain endpoints stay available.
- Admin routes are additive and frontend-facing.
- Prefer path-scoped admin payloads when the parent resource id is already in the URL.

## Deferred

- Authentication.
- Role-based permissions.
- Admin audit fields such as `created_by_user_id`.
- Dashboard trend charts, breakdowns, and materialized reporting tables.
