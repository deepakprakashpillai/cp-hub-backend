# Teacher Domain

An existing admin account can be granted the teacher role and linked to a teacher profile without
creating another user. Teacher portal access still requires the role and an active profile and is
scoped to that profile. See [Users](users.md) for the role and profile-linking API.

## Purpose

The teacher domain manages teacher profiles, recurring availability rules, manual bookable slots, blocked time, and generated bookable slots.

Teacher deactivation is coordinated by `TeacherLifecycleWorkflow`, which clears affected permanent
student assignments and publishes notifications in the same transaction.

## Implemented Models

### `teachers`

Fields:

- `id`
- `user_id`
- `display_name`
- `bio`
- `profile_photo_url`
- `is_active`
- `created_at`
- `updated_at`

Rules:

- A teacher profile must link to an existing user.
- The linked user must have the teacher role among its assigned roles.
- One user can have only one teacher profile.
- `teachers.is_active` means the teacher profile can be enabled/paused separately from the user account.
- Deactivating a teacher clears permanent one-on-one student assignments to that teacher.

### `teacher_availability_rules`

Stores recurring weekly availability templates.

Fields:

- `id`
- `teacher_id`
- `day_of_week`
- `start_time_utc`
- `end_time_utc`
- `slot_duration_minutes`
- `is_active`
- `created_at`
- `updated_at`

Rules:

- Rule times are stored as UTC times.
- Frontend is responsible for converting local display time into UTC before sending.
- `start_time_utc` must be before `end_time_utc`.
- Rules are soft-deleted by setting `is_active = false`.

### `teacher_availability_slots`

Stores actual bookable/blockable slot records.

Fields:

- `id`
- `teacher_id`
- `rule_id`
- `source`
- `starts_at`
- `ends_at`
- `status`
- `created_at`
- `updated_at`

Allowed `source` values:

- `rule`
- `manual`

Allowed `status` values:

- `available`
- `booked`
- `cancelled`
- `blocked`

Rules:

- Slot datetimes are stored in UTC.
- Manual slots have `source = manual` and `rule_id = null`.
- Rule-generated slots have `source = rule` and must include `rule_id`.
- A teacher cannot have overlapping active slots.
- `cancelled` slots do not block future slots.
- Booked slots cannot be edited or deleted.
- Deleting a slot marks it `cancelled`; it is not hard-deleted.
- A partial unique index prevents duplicate active exact slots for the same teacher/time range.

## Teacher Profile APIs

Authenticated teacher portal APIs are under `/api/v1/teacher/me`. They return and mutate only the
signed-in teacher's profile and availability, expose only classes assigned to that teacher, and
enforce that roster, attendance, and booking-note operations belong to one of those classes.
`GET /teacher/me` uses the nested `{user, teacher}` shape. Class list/detail responses include
teacher, batch, primary-student, and booking-status projections; roster entries include the
student identity. `GET /teacher/me/students` returns the same nested student projection used by
the admin portal, constrained to permanent assignments for the signed-in teacher.

Teacher class-session mutations:

- `PATCH /api/v1/teacher/me/classes/{class_session_id}/schedule` changes only an assigned, future,
  scheduled batch-day option. The replacement time must remain on the option's existing UTC batch
  date and passes the normal batch-option overlap and active-booking validations.
- `POST /api/v1/teacher/me/classes/{class_session_id}/cancel` cancels only that assigned, future,
  scheduled batch-day option and its active bookings. Each cancelled booking records
  `cancelled_by_teacher` with the authenticated teacher user as actor and the supplied reason.

Base path:

```txt
/api/v1/teachers
```

Endpoints:

- `GET /api/v1/teachers`
- `POST /api/v1/teachers`
- `GET /api/v1/teachers/{teacher_id}`

`GET /api/v1/teachers` is paginated with `page` and `page_size`.

Admin orchestration endpoint:

- `POST /api/v1/admin/teachers` creates the teacher user and linked teacher profile atomically.
- `POST /api/v1/admin/teachers/link-existing` links an existing admin account atomically, as
  described below.
- `GET /api/v1/admin/teachers` and `GET /api/v1/admin/teachers/{teacher_id}` return teacher
  profile data nested with the linked user data.
- `PATCH /api/v1/admin/teachers/{teacher_id}` updates teacher profile fields and returns teacher
  profile data nested with the linked user data.
- `GET /api/v1/admin/teachers` supports `q` search across teacher `display_name` and linked user
  `full_name`, `email`, and `phone`.
- `GET /api/v1/admin/teachers` supports `is_active` filtering by teacher profile active state.
- `GET /api/v1/admin/teachers` supports independent `account_is_active` filtering by linked user
  account state.
- Admin teacher sorting supports `created_at`, linked-user `name`, teacher `display_name`, and
  teacher-profile `is_active`, with `asc` or `desc` direction.
- Admin teacher sorting defaults to `created_at desc` and uses teacher ID as a stable tiebreaker.

### Link an existing admin as a teacher

An authenticated admin can call `POST /api/v1/admin/teachers/link-existing` with:

```json
{
  "user_id": "existing-admin-user-uuid",
  "display_name": "Teacher display name",
  "bio": null,
  "profile_photo_url": null,
  "is_active": true
}
```

`user_id` and `display_name` are required; the remaining fields are optional, and `is_active`
defaults to true. A 200 response contains `{ "user": UserRead, "teacher": TeacherRead,
"profile_already_existed": boolean }`. The caller may select their own account. The target must
already have the admin role; disabled accounts are allowed and remain disabled. If a profile
exists, it is returned unchanged (including its active state), and the submitted profile fields
are ignored. The teacher role is assigned in either case. No password invitation is sent, and the
existing credentials, admin role and account status are preserved.

Missing targets return 404, targets without the admin role return 409, malformed input returns
422, unauthenticated callers return 401, and non-admin callers return 403. A row lock serializes
role changes and profile creation, including concurrent retries and the legacy teacher creation
path; the existing unique profile constraint remains a safeguard. Both role assignment and profile
creation commit together or roll back together. No new database migration is required. See
[Users](users.md) for the exact email lookup used to choose the account.

Admin teacher profile update fields:

- `display_name`
- `bio`
- `profile_photo_url`
- `is_active`

## Booking Feedback APIs

Endpoints:

- `POST /api/v1/teacher/bookings/{booking_id}/notes`
- `GET /api/v1/teacher/bookings/{booking_id}/notes`
- `PATCH /api/v1/teacher/booking-notes/{note_id}`

Rules:

- The authenticated teacher identity is derived from the access token; clients do not send a
  `teacher_id`.
- Create payloads include note text and optional visibility.
- The teacher must be assigned to the booking's linked class session.
- New notes are allowed only at or after class start.
- Visibility defaults to `admin_only`; `student_visible` is supported for future student portal use.
- Teachers can update only notes they own and only while they remain assigned to the class.
- Feedback does not change booking status, class status, attendance, or booking event history.

## Availability APIs

Base path:

```txt
/api/v1/schedules/teacher-availability
```

Rule endpoints:

- `GET /api/v1/schedules/teacher-availability/rules`
- `POST /api/v1/schedules/teacher-availability/rules`
- `GET /api/v1/schedules/teacher-availability/rules/{rule_id}`
- `PATCH /api/v1/schedules/teacher-availability/rules/{rule_id}`
- `DELETE /api/v1/schedules/teacher-availability/rules/{rule_id}`

Slot endpoints:

- `GET /api/v1/schedules/teacher-availability/slots`
- `POST /api/v1/schedules/teacher-availability/slots`
- `POST /api/v1/schedules/teacher-availability/slots/bulk`
- `POST /api/v1/schedules/teacher-availability/blocks`
- `GET /api/v1/schedules/teacher-availability/slots/{slot_id}`
- `PATCH /api/v1/schedules/teacher-availability/slots/{slot_id}`
- `DELETE /api/v1/schedules/teacher-availability/slots/{slot_id}`

Admin availability aliases:

- `GET /api/v1/admin/teacher-availability/rules`
- `POST /api/v1/admin/teacher-availability/rules`
- `GET /api/v1/admin/teacher-availability/rules/{rule_id}`
- `PATCH /api/v1/admin/teacher-availability/rules/{rule_id}`
- `DELETE /api/v1/admin/teacher-availability/rules/{rule_id}`
- `GET /api/v1/admin/teacher-availability/slots`
- `POST /api/v1/admin/teacher-availability/slots`
- `POST /api/v1/admin/teacher-availability/slots/bulk`
- `POST /api/v1/admin/teacher-availability/blocks`
- `GET /api/v1/admin/teacher-availability/slots/{slot_id}`
- `PATCH /api/v1/admin/teacher-availability/slots/{slot_id}`
- `DELETE /api/v1/admin/teacher-availability/slots/{slot_id}`

Slot listing filters:

- `teacher_id`
- `starts_from`
- `starts_to`
- `status` on the admin alias
- `source` on the admin alias
- `sort_order` on the admin alias

Availability rule and slot list endpoints are paginated with `page` and `page_size`.
Admin availability aliases reuse the existing schedule service behavior.
Admin slot listing sorts by `starts_at`, defaults to ascending, and uses slot ID as a stable
tiebreaker.

## Slot Generation

Reusable generation logic lives in:

```txt
app/modules/schedules/slot_generation.py
```

Standalone command:

```bash
uv run generate-teacher-slots
```

Admin per-teacher generation endpoint:

```txt
POST /api/v1/admin/teachers/{teacher_id}/availability/generate
```

Generation behavior:

- Generates actual slots from active availability rules.
- Window is now through today + 14 days.
- If today is Monday, slots can be generated through the Monday two weeks later.
- Past slots are skipped.
- If current time is 09:15, a 09:00 slot is skipped and the next valid slot starts at 10:00.
- Manual blocked slots win over generated slots.
- Manual available slots win over generated slots.
- Existing active exact slots are not duplicated.
- Future available generated slots that no longer match a changed/deleted rule are cancelled.
- Booked slots are preserved.
- One-on-one booking marks the selected teacher availability slot as `booked`.
- Program-switch cancellation can release a future one-on-one booked slot back to `available`.

Invocation behavior:

- Rule create calls slot generation immediately.
- Rule update calls slot generation immediately.
- Rule delete deactivates the rule and calls slot generation immediately.
- The standalone command can be run nightly by cron or a hosting scheduler as a backup/repair job.
- The admin per-teacher generation endpoint accepts `days_ahead`, default `14`, minimum `1`,
  maximum `90`.
- The admin per-teacher generation endpoint returns `rules_checked`, `slots_created`,
  `slots_cancelled`, and `slots_skipped`.

## Files

- `app/modules/teachers/models.py`
- `app/modules/teachers/schemas.py`
- `app/modules/teachers/service.py`
- `app/modules/teachers/routes.py`
- `app/modules/schedules/models.py`
- `app/modules/schedules/schemas.py`
- `app/modules/schedules/service.py`
- `app/modules/schedules/routes.py`
- `app/modules/schedules/slot_generation.py`
- `app/commands/generate_teacher_slots.py`
- `tests/modules/schedules/test_slot_generation.py`

## Migrations

- `alembic/versions/20260719_0002_create_teachers_table.py`
- `alembic/versions/20260719_0003_create_teacher_availability.py`
- `alembic/versions/20260719_0004_add_active_slot_unique_index.py`

## Deferred

- Tracking who created/blocked/cancelled a slot.
- Production scheduler configuration.
- Strong Postgres exclusion constraint for partial time overlaps.
- Teacher delete profile APIs.
