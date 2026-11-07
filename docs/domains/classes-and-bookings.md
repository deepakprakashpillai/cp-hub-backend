# Classes And Bookings Domain

## Status

Core class sessions and bookings foundation implemented.

Implemented files:

- `app/modules/classes/models.py`
- `app/modules/classes/schemas.py`
- `app/modules/classes/service.py`
- `app/modules/classes/routes.py`
- `app/modules/batch_groups/models.py`
- `app/modules/batch_groups/schemas.py`
- `app/modules/batch_groups/service.py`
- `app/modules/batch_groups/lifecycle_service.py`
- `app/modules/batch_groups/membership_service.py`
- `app/modules/batch_groups/session_generation_service.py`
- `app/modules/batch_groups/routes.py`
- `app/modules/bookings/models.py`
- `app/modules/bookings/schemas.py`
- `app/modules/bookings/service.py`
- `app/modules/bookings/query_service.py`
- `app/modules/bookings/creation_service.py`
- `app/modules/bookings/cancellation_service.py`
- `app/modules/bookings/reschedule_service.py`
- `app/modules/bookings/attendance_service.py`
- `app/modules/bookings/routes.py`

Batch schedule-day behavior is separated into query, lifecycle, and option services. Shared
validation and locking helpers remain private to their feature packages.

## Core Model

The domain separates availability supply from actual classes:

```txt
teacher_availability_slot = teacher supply
class_session = actual class occurrence
booking = student's seat in a class_session
```

Both one-on-one and batch classes use `class_sessions`.

Both one-on-one and batch bookings use `bookings`.

Batch students are grouped through batch groups:

```txt
batch_group = group of students
student_batch_membership = student's active or historical batch assignment
batch class_session = one generated timing option for a batch group
```

## Implemented Models

### `class_sessions`

Stores actual scheduled class occurrences.

Fields:

- `id`
- `teacher_id`
- `teacher_availability_slot_id`
- `batch_group_id`
- `batch_schedule_day_id`
- `program_type`
- `batch_slot`
- `display_label`
- `option_order`
- `starts_at`
- `ends_at`
- `status`
- `capacity`
- `created_at`
- `updated_at`

Allowed `program_type` values:

- `one_on_one`
- `batch`

Allowed `batch_slot` values:

- `morning`
- `noon`
- `afternoon`

Allowed `status` values:

- `scheduled`
- `completed`
- `cancelled`

Rules:

- `starts_at` and `ends_at` are stored in UTC.
- `starts_at` must be before `ends_at`.
- `capacity` must be greater than 0.
- One-on-one class sessions must have `teacher_id`.
- One-on-one class sessions must have `teacher_availability_slot_id`.
- One-on-one class sessions must have `capacity = 1`.
- One-on-one class sessions must have `batch_slot = null`.
- Batch class sessions must have either legacy `batch_slot` or a custom `display_label`.
- New batch-day option sessions can use a custom `display_label` instead of `batch_slot`.
- Batch-day options link to `batch_schedule_days` and use `option_order` for stable display.
- Batch class sessions must have `teacher_availability_slot_id = null`.
- Batch class sessions must have `batch_group_id`.
- Batch class sessions can have `teacher_id = null` so admin can create sessions before teacher assignment.
- Non-cancelled class sessions for the same batch group cannot overlap in time.
- A teacher availability slot can have only one non-cancelled one-on-one class session.
- One-on-one class sessions are created by the booking flow, not by the public class creation endpoint.
- Batch class sessions are created through the class session API.

### `bookings`

Stores a student's booking into a class session.

Fields:

- `id`
- `student_id`
- `class_session_id`
- `status`
- `booked_at`
- `created_at`
- `updated_at`

Allowed `status` values:

- `booked`
- `cancelled`
- `attended`
- `missed`

Rules:

- A booking must link to an existing student.
- A booking must link to an existing class session.
- A student cannot have duplicate non-cancelled bookings for the same class session.
- A student can have max one booked scheduled class per UTC day.
- `booked_at` is stored as a timezone-aware UTC datetime.

### `booking_events`

Stores the log of booking-level actions.

Fields:

- `id`
- `booking_id`
- `event_type`
- `actor_user_id`
- `reason`
- `metadata`
- `created_at`
- `updated_at`

Allowed `event_type` values:

- `booked`
- `cancelled_by_student`
- `cancelled_by_admin`
- `cancelled_by_teacher`
- `rescheduled_from`
- `rescheduled_to`
- `class_cancelled_empty`
- `attendance_marked`
- `manually_added_by_admin`

Rules:

- A booking event must link to an existing booking.
- `actor_user_id` is optional for system-generated and legacy service-level events; authenticated
  portal actions populate it from the current user.
- `actor_user_id` must link to an existing user when provided.
- `reason` is always stored.
- The backend supplies default reasons when the request omits one.
- Automatic batch empty-class cancellation uses reason `empty class`.

### `booking_notes`

Stores teacher-authored feedback for a student's booking and class.

Fields:

- `id`
- `booking_id`
- `class_session_id`
- `student_id`
- `teacher_id`
- `note`
- `visibility`
- `created_at`
- `updated_at`

Allowed `visibility` values:

- `admin_only`
- `student_visible`

Rules:

- Booking, class session, and student references are derived from the selected booking.
- The note author must be the teacher assigned to the booking's class session.
- Notes can be created only at or after the class start time.
- Note text is required, trimmed, and limited to 2000 characters.
- Visibility defaults to `admin_only`.
- Notes do not replace booking events and do not change booking or class status.
- Teacher update and list operations derive ownership from the authenticated teacher.
- Admin can read all notes for a booking.

### `batch_groups`

Stores named groups of batch students.

Fields:

- `id`
- `name`
- `package_id`
- `default_capacity`
- `is_active`
- `notes`
- `created_at`
- `updated_at`

Rules:

- `default_capacity` must be greater than 0.
- Active batch group names must be unique.
- A package can be linked to multiple batch groups. Existing migrated groups may remain unlinked.
- New active groups and newly activated groups require an active package.
- Active groups reject assignment of an inactive package, and linked packages cannot be voided
  while an active group references them.
- Changing a group's package does not alter existing student access, memberships, or bookings.
- Batch groups are voided by setting `is_active = false`.
- Voiding a batch group cancels future scheduled sessions for that group.
- Voiding a batch group cancels future booked bookings for that group.

### `student_batch_memberships`

Stores current and historical student-to-batch-group assignments.

Fields:

- `id`
- `student_id`
- `batch_group_id`
- `is_active`
- `assigned_by_user_id`
- `assigned_at`
- `ended_at`
- `end_reason`
- `created_at`
- `updated_at`

Rules:

- Only batch students can be assigned to a batch group through normal membership APIs.
- New assignment or transfer requires a currently valid access grant linked to the destination
  group's package.
- Admin can explicitly bypass only this package-grant match with
  `allow_package_access_override = true` and a non-empty reason.
- New membership in an unconfigured legacy group also requires that explicit override.
- A student can have only one active batch membership.
- Batch transfer ends the old active membership and creates a new active membership.
- Batch transfer cancels future booked bookings from the old batch group.
- Switching a student from `batch` to `one_on_one` ends their active batch membership.

### `batch_schedule_days`

Groups selectable batch class-session options for one batch group and UTC calendar date.

Fields:

- `id`
- `batch_group_id`
- `schedule_date`
- `created_by_user_id`
- `created_at`
- `updated_at`

Rules:

- One parent exists per batch group and UTC date.
- Each child option is a normal batch `class_session`.
- New options use arbitrary `display_label` values and stable `option_order`.
- Existing `batch_slot` remains available for backward compatibility.
- Existing batch sessions are backfilled into UTC-date parents.

### `batch_schedule_defaults`

Stores the singleton admin scheduling defaults.

Fields:

- `timezone`, always the read-only value `UTC`
- `default_option_count`
- `default_teacher_id`
- `capacity_strategy`
- `fixed_capacity`
- `option_templates`

The seeded templates are Morning `08:00`, Noon `12:00`, and Evening `18:00`, each with a
60-minute duration.

## Implemented One-On-One Booking Flow

Endpoint:

```txt
POST /api/v1/bookings/one-on-one
```

Request fields:

- `student_id`
- `teacher_availability_slot_id`

Rules:

- Student must exist.
- Student must have `program_type = one_on_one`.
- Student must have `status = active`.
- Student access window must be currently valid.
- Teacher availability slot must exist.
- Teacher availability slot must have `status = available`.
- Teacher availability slot must start in the future.
- Student must not already have a booked scheduled class on that UTC day.
- Booking creates a one-on-one `class_session`.
- Booking creates a `booking`.
- Booking marks the teacher availability slot as `booked`.
- Booking logs a `booked` booking event.

## Implemented Batch Class Flow

Create batch class endpoint:

```txt
POST /api/v1/classes/batch
POST /api/v1/admin/classes/batch
```

Request fields:

- `batch_group_id`
- `teacher_id`
- `batch_slot`
- `starts_at`
- `ends_at`
- `status`
- `capacity`

Batch booking endpoint:

```txt
POST /api/v1/bookings/batch
PUT /api/v1/students/{student_id}/batch-schedule-days/{day_id}/selection
```

Request fields:

- `student_id`
- `class_session_id`

Rules:

- Student must exist.
- Student must have `program_type = batch`.
- Student must have `status = active`.
- Student access window must be currently valid.
- Student must have an active batch membership.
- Class session must exist.
- Class session must have `program_type = batch`.
- Class session must belong to the student's active batch group.
- Class session must have `status = scheduled`.
- Class session must start in the future.
- Batch booking window closes three hours before class start.
- Student must not already have a booked scheduled class on that UTC day.
- Batch capacity is enforced from active `booked` bookings.
- Booking logs a `booked` booking event.
- Batch-day selection locks the student, enforces one active option for the parent, and evaluates
  the general daily limit using the parent's UTC date.
- Student selection requires access to cover the selected option's start time.
- Student selection logs `selected_by_student` with source and batch-day metadata.
- Admin assignment, movement, and removal log `assigned_by_admin`, `moved_by_admin`, and
  `removed_by_admin`.
- Admin movement cancels the old booking and creates the new booking atomically.
- Cancelling/removing a batch-day selection does not cancel the selectable session option.

## Implemented Cancellation And Reschedule Flow

Student cancellation endpoint:

```txt
POST /api/v1/bookings/{booking_id}/cancel
```

Admin cancellation endpoint:

```txt
POST /api/v1/bookings/{booking_id}/admin-cancel
POST /api/v1/admin/bookings/{booking_id}/cancel
```

Student reschedule endpoints:

```txt
POST /api/v1/bookings/{booking_id}/reschedule/one-on-one
POST /api/v1/bookings/{booking_id}/reschedule/batch
```

Admin reschedule endpoints:

```txt
POST /api/v1/bookings/{booking_id}/admin-reschedule/one-on-one
POST /api/v1/bookings/{booking_id}/admin-reschedule/batch
POST /api/v1/admin/bookings/{booking_id}/reschedule/one-on-one
POST /api/v1/admin/bookings/{booking_id}/reschedule/batch
```

Admin class cancellation endpoint:

```txt
POST /api/v1/admin/classes/{class_session_id}/cancel
```

Teacher batch-option endpoints:

```txt
PATCH /api/v1/teacher/me/classes/{class_session_id}/schedule
POST /api/v1/teacher/me/classes/{class_session_id}/cancel
```

Event listing endpoint:

```txt
GET /api/v1/bookings/{booking_id}/events
```

Rules:

- Student cancellation and reschedule are allowed only until 24 hours before class start.
- Admin cancellation and reschedule can happen anytime while the booking is still `booked`.
- Cancellation and reschedule requests can include `actor_user_id`.
- `actor_user_id` is validated when provided.
- Cancellation and reschedule requests can include `reason`.
- Student cancellation default reason is `cancelled by student`.
- Admin cancellation default reason is `cancelled by admin`.
- Reschedule default reason is `rescheduled`.
- One-on-one cancellation marks the booking `cancelled`.
- One-on-one cancellation marks the class session `cancelled`.
- Future one-on-one cancellation releases the teacher availability slot back to `available`.
- Batch cancellation marks only that student's booking `cancelled`.
- Batch cancellation leaves the class session scheduled while at least one active booked student remains.
- Batch cancellation marks the class session `cancelled` if zero active booked students remain.
- Empty batch class cancellation logs `class_cancelled_empty` with reason `empty class`.
- Admin class cancellation marks a scheduled class session `cancelled`.
- Admin class cancellation marks all active `booked` bookings for that class `cancelled`.
- Admin class cancellation logs `cancelled_by_admin` booking events for every cancelled booking.
- A teacher can change or cancel only a future scheduled batch option assigned to them. Schedule
  changes retain the UTC batch-day date, preserve active bookings, and log reschedule audit events
  with the teacher as actor. Teacher cancellation affects only the selected option and its active
  bookings, logging `cancelled_by_teacher` with the teacher actor and reason.
- Admin class cancellation rejects completed and already-cancelled classes.
- Admin class cancellation reopens a future one-on-one linked teacher availability slot when the
  slot is still `booked`.
- Admin class-level reschedule is implemented for both program types.
- Reschedule is implemented as cancel old booking, then create new booking through normal booking logic.
- Reschedule logs `rescheduled_from` on the old booking.
- Reschedule logs `rescheduled_to` on the new booking.

Class-level reschedule endpoints:

```txt
POST /api/v1/admin/classes/{class_session_id}/reschedule/one-on-one
POST /api/v1/admin/classes/{class_session_id}/reschedule/batch
```

Rules:

- One-on-one class reschedule reuses the active booking's existing admin reschedule flow, so it
  cancels the old class/booking and creates the replacement from the selected teacher slot.
- The one-on-one response contains the resulting class projection and booking.
- Batch class reschedule mutates the existing class session and preserves all active `booked`
  booking IDs.
- Batch class reschedule rejects completed, cancelled, or started classes and destination start
  times that are not in the future.
- Batch class reschedule rejects invalid time ranges, batch-group overlaps, teacher overlaps,
  capacity below active booked count, and student UTC-day conflicts.
- Optional teacher, batch slot, and capacity values preserve the existing value when omitted.
  Explicit null can clear the teacher but cannot clear batch slot or capacity.
- Every preserved active booking receives `rescheduled_from` and `rescheduled_to` events containing
  old and new schedule metadata.
- The batch class update and all booking events are atomic.

## Implemented Attendance Flow

Single-booking attendance endpoint:

```txt
POST /api/v1/bookings/{booking_id}/attendance
```

Bulk class attendance endpoint:

```txt
POST /api/v1/classes/{class_session_id}/attendance
POST /api/v1/admin/classes/{class_session_id}/attendance
```

Rules:

- Attendance is stored on `bookings.status`.
- `booked` means attendance is not marked yet.
- `attended` means present.
- `missed` means absent.
- `cancelled` means cancelled and cannot be marked attended or missed.
- Attendance can be marked only after class start.
- Teacher marks attendance.
- Admin can correct attendance later.
- Auth is deferred, so attendance requests accept optional `actor_user_id`.
- `actor_user_id` is validated when provided.
- Single-booking attendance is used for one-on-one classes and corrections.
- Bulk class attendance is used for batch classes.
- Bulk class attendance can mark selected bookings for that class.
- Attendance endpoint can set only `attended` or `missed`.
- Default reason for `attended` is `present`.
- Default reason for `missed` is `absent`.
- Attendance updates log `attendance_marked` booking events.
- Attendance event metadata stores old and new booking status.
- When all non-cancelled bookings in a class are `attended` or `missed`, the class session becomes `completed`.
- No automatic no-show job is implemented.

## Implemented Admin Manual Add Flow

Endpoint:

```txt
POST /api/v1/classes/{class_session_id}/admin-add-student
POST /api/v1/admin/classes/{class_session_id}/students
```

Request fields:

- `student_id`
- `actor_user_id`
- `reason`

Rules:

- Admin manual add works for one-on-one and batch class sessions.
- Admin can override student program type mismatch.
- Admin can override batch group mismatch.
- Student must still have `status = active`.
- Student must still have a currently valid access window.
- Admin cannot overbook a class session.
- Admin can manually add a student after class start.
- Class session must still be `scheduled`.
- Student cannot already have a non-cancelled booking for the same class session.
- Student cannot already have another non-cancelled class on the same UTC day.
- Manual add creates a `booked` booking.
- Manual add logs `manually_added_by_admin`.
- Default reason is `manually added by admin`.

## Implemented Batch Generation Flow

Endpoint:

```txt
POST /api/v1/batch-groups/{batch_group_id}/sessions/generate
POST /api/v1/admin/batch-groups/{batch_group_id}/sessions/generate
```

Request fields:

- `starts_from`
- `starts_to`
- `weekdays`
- `sessions`

Each session template contains:

- `batch_slot`
- `start_time_utc`
- `end_time_utc`
- `teacher_id`
- `capacity`

Rules:

- Backend only deals with UTC dates and times.
- Admin chooses weekdays.
- Date range can include up to 90 calendar dates.
- The legacy generator accepts its existing slot templates and associates generated sessions with
  UTC batch-day parents.
- Admin can choose any subset of `morning`, `noon`, and `afternoon`.
- Session capacity overrides `batch_group.default_capacity`.
- If session capacity is omitted, `batch_group.default_capacity` is used.
- Cross-midnight UTC sessions are allowed.
- Cross-midnight sessions count by `starts_at` UTC date for daily booking limits.
- If any generated session overlaps another generated session for the same request, the whole request is rejected.
- If any generated session overlaps an existing non-cancelled session for the same batch group, the whole request is rejected.

## Program Switch Integration

When a student's program type is switched:

- Future `booked` bookings for the student are marked `cancelled`.
- Future one-on-one class sessions created for that student are marked `cancelled`.
- Future one-on-one teacher availability slots released by that cancellation are marked `available`.
- Future booking cancellations from program switch are logged as booking events.
- Batch class sessions remain scheduled when one student's booking is cancelled.
- Switching from `batch` to `one_on_one` ends the student's active batch membership.

When a student is transferred to another batch group:

- Old active membership is ended.
- New active membership is created.
- Future booked bookings from the old batch group are cancelled.
- Future booking cancellations from batch transfer are logged as booking events.

When an admin removes a student from a batch group without transferring them:

- The active membership for that exact student/group is ended.
- Future `booked` bookings for that student in that group are cancelled.
- Each cancellation logs `cancelled_by_admin`.
- The student remains `program_type = batch` and may temporarily have no active group.
- The membership and booking changes commit atomically.

## APIs

Class session base path:

```txt
/api/v1/classes
```

Endpoints:

- `GET /api/v1/classes`
- `GET /api/v1/classes?program_type={program_type}`
- `GET /api/v1/classes?starts_from={datetime}&starts_to={datetime}`
- `GET /api/v1/admin/classes`
- `GET /api/v1/admin/classes?q={search}`
- `GET /api/v1/admin/classes?status={status}`
- `GET /api/v1/admin/classes?teacher_id={teacher_id}`
- `GET /api/v1/admin/classes?batch_group_id={batch_group_id}`
- `POST /api/v1/classes/batch`
- `POST /api/v1/admin/classes/batch`
- `POST /api/v1/classes/{class_session_id}/attendance`
- `POST /api/v1/admin/classes/{class_session_id}/attendance`
- `POST /api/v1/classes/{class_session_id}/admin-add-student`
- `POST /api/v1/admin/classes/{class_session_id}/students`
- `POST /api/v1/admin/classes/{class_session_id}/cancel`
- `POST /api/v1/admin/classes/{class_session_id}/reschedule/one-on-one`
- `POST /api/v1/admin/classes/{class_session_id}/reschedule/batch`
- `GET /api/v1/admin/classes/{class_session_id}/roster`
- `GET /api/v1/admin/classes/{class_session_id}/activity`
- `GET /api/v1/classes/{class_session_id}`
- `GET /api/v1/admin/classes/{class_session_id}`

Class session list endpoints are paginated with `page` and `page_size`.
Admin class list filters can be combined and support `program_type`, `starts_from`, `starts_to`,
`status`, `teacher_id`, `batch_group_id`, `q`, and `sort_order`.
Admin class sorting uses `class_sessions.starts_at`, defaults to `asc`, supports `desc` for
reverse-chronological history, and uses class-session ID as a deterministic secondary sort.
Admin class reads add compact teacher, batch-group, primary one-on-one student, and booking-status
count projections without changing the underlying class-session fields. The paginated roster
returns booking fields plus compact nested student/user identity.
The admin class activity endpoint aggregates events across every session booking into a single
newest-first audit timeline. It joins student and optional actor identity in the paginated query,
uses `System` as the actor label when no actor is stored, and orders by event creation time then
event ID descending. Existing per-booking event endpoints are unchanged.

Batch group base path:

```txt
/api/v1/batch-groups
```

Endpoints:

- `GET /api/v1/batch-groups`
- `GET /api/v1/batch-groups?is_active={bool}`
- `GET /api/v1/admin/batch-groups`
- `POST /api/v1/admin/batch-groups`
- `POST /api/v1/batch-groups`
- `GET /api/v1/batch-groups/{batch_group_id}`
- `GET /api/v1/admin/batch-groups/{batch_group_id}`
- `PATCH /api/v1/batch-groups/{batch_group_id}`
- `PATCH /api/v1/admin/batch-groups/{batch_group_id}`
- `POST /api/v1/batch-groups/{batch_group_id}/void`
- `POST /api/v1/admin/batch-groups/{batch_group_id}/void`
- `GET /api/v1/batch-groups/{batch_group_id}/students`
- `GET /api/v1/batch-groups/{batch_group_id}/students?is_active={bool}`
- `GET /api/v1/admin/batch-groups/{batch_group_id}/students`
- `POST /api/v1/admin/batch-groups/{batch_group_id}/students`
- `DELETE /api/v1/admin/batch-groups/{batch_group_id}/students/{student_id}`
- `POST /api/v1/batch-groups/{batch_group_id}/students`
- `POST /api/v1/batch-groups/{batch_group_id}/sessions/generate`
- `POST /api/v1/admin/batch-groups/{batch_group_id}/sessions/generate`

Student batch membership endpoints:

- `POST /api/v1/students/{student_id}/batch-transfer`
- `GET /api/v1/students/{student_id}/batch-memberships`

Batch group and membership list endpoints are paginated with `page` and `page_size`.
The admin batch-group list additionally supports `q`, `is_active`, `sort_by`, and `sort_order`,
and returns `active_member_count` plus `upcoming_scheduled_count`. Filtering, aggregate sorting,
and deterministic ID ordering happen before pagination.

Batch schedule-day endpoints:

- `GET /api/v1/admin/batch-schedule-defaults`
- `PATCH /api/v1/admin/batch-schedule-defaults`
- `GET /api/v1/admin/batch-schedule-days`
- `POST /api/v1/admin/batch-schedule-days`
- `POST /api/v1/admin/batch-schedule-days/bulk`
- `POST /api/v1/admin/batch-schedule-days/cancel-bulk`
- `GET /api/v1/admin/batch-schedule-days/{day_id}`
- `POST /api/v1/admin/batch-schedule-days/{day_id}/cancel`
- `POST /api/v1/admin/batch-schedule-days/{day_id}/options`
- `PATCH /api/v1/admin/batch-schedule-days/{day_id}/options/{class_session_id}`
- `DELETE /api/v1/admin/batch-schedule-days/{day_id}/options/{class_session_id}`
- `PUT /api/v1/admin/batch-schedule-days/{day_id}/students/{student_id}`
- `DELETE /api/v1/admin/batch-schedule-days/{day_id}/students/{student_id}`
- `GET /api/v1/students/{student_id}/batch-schedule-days`
- `PUT /api/v1/students/{student_id}/batch-schedule-days/{day_id}/selection`

All schedule dates and option times use UTC. Day cancellation is soft-delete lifecycle behavior:
scheduled child sessions and their active bookings are cancelled atomically, completed sessions
are preserved, and day-level plus per-booking audit events retain actor and reason. Cancelled
options remain in the admin day projection for audit.

Booking base path:

```txt
/api/v1/bookings
```

Endpoints:

- `GET /api/v1/bookings`
- `GET /api/v1/bookings?student_id={student_id}`
- `GET /api/v1/bookings?class_session_id={class_session_id}`
- `GET /api/v1/admin/bookings`
- `GET /api/v1/admin/bookings?status={status}`
- `GET /api/v1/admin/bookings?teacher_id={teacher_id}`
- `GET /api/v1/admin/bookings?starts_from={datetime}&starts_to={datetime}`
- `POST /api/v1/bookings/one-on-one`
- `POST /api/v1/admin/bookings/one-on-one`
- `POST /api/v1/bookings/batch`
- `POST /api/v1/bookings/{booking_id}/cancel`
- `POST /api/v1/bookings/{booking_id}/admin-cancel`
- `POST /api/v1/admin/bookings/{booking_id}/cancel`
- `POST /api/v1/bookings/{booking_id}/reschedule/one-on-one`
- `POST /api/v1/bookings/{booking_id}/reschedule/batch`
- `POST /api/v1/bookings/{booking_id}/admin-reschedule/one-on-one`
- `POST /api/v1/bookings/{booking_id}/admin-reschedule/batch`
- `POST /api/v1/admin/bookings/{booking_id}/reschedule/one-on-one`
- `POST /api/v1/admin/bookings/{booking_id}/reschedule/batch`
- `GET /api/v1/bookings/{booking_id}/events`
- `GET /api/v1/admin/bookings/{booking_id}/events`
- `GET /api/v1/admin/bookings/{booking_id}/notes`
- `POST /api/v1/bookings/{booking_id}/attendance`
- `GET /api/v1/bookings/{booking_id}`
- `GET /api/v1/admin/bookings/{booking_id}`

Booking, booking event, and booking note list endpoints are paginated with `page` and `page_size`.
Admin booking list filters can be combined and support `student_id`, `class_session_id`, `status`,
`teacher_id`, `starts_from`, and `starts_to`.
Admin booking `starts_from` and `starts_to` filter by linked `class_sessions.starts_at`, not the
booking creation time.

## Deferred

- Whether package/access changes affect existing future bookings beyond program switch cancellation.
