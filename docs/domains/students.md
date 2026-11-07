# Students Domain

## Status

Student admin foundation implemented.

Implemented files:

- `app/modules/students/models.py`
- `app/modules/students/schemas.py`
- `app/modules/students/service.py`
- `app/modules/students/workflows.py`
- `app/modules/students/routes.py`
- `app/modules/packages/models.py`
- `app/modules/packages/schemas.py`
- `app/modules/packages/service.py`
- `app/modules/packages/routes.py`
- `app/modules/student_payments/models.py`
- `app/modules/student_payments/schemas.py`
- `app/modules/student_payments/service.py`
- `app/modules/student_payments/routes.py`
- `app/modules/student_access_grants/models.py`
- `app/modules/student_access_grants/schemas.py`
- `app/modules/student_access_grants/service.py`
- `app/modules/student_access_grants/routes.py`

## Implemented Models

Cross-feature program switching is owned by `StudentProgramWorkflow`. It cancels future bookings,
updates batch membership and permanent teacher assignment as required, records the program change,
and commits the complete transition once.

### `students`

Stores the student profile linked to a login/user identity.

Fields:

- `id`
- `user_id`
- `program_type`
- `assigned_teacher_id`
- `status`
- `access_starts_at`
- `access_ends_at`
- `joined_at`
- `notes`
- `created_at`
- `updated_at`

Allowed `program_type` values:

- `one_on_one`
- `batch`

Allowed `status` values:

- `enrolled`
- `active`
- `paused`
- `completed`
- `cancelled`

Rules:

- A student profile must link to an existing user.
- The linked user must have `role = student`.
- One user can have only one student profile.
- Student program can be switched by an admin later.
- `joined_at` means the date/time the admin created the student profile.
- `enrolled` students can log in but cannot book classes.
- `active` students can book only while their access window is valid.
- `paused`, `completed`, and `cancelled` students can log in but cannot book.
- Expiry is computed from the access window, not stored as a permanent status.
- Booking eligibility should use `status = active`, `now >= access_starts_at`, and `now < access_ends_at`.
- `access_ends_at` is treated as exclusive next-midnight UTC.
- An `active` student must have both `access_starts_at` and `access_ends_at`.
- `assigned_teacher_id` is an optional permanent teacher assignment for one-on-one students.
- A batch student cannot have an assigned teacher.
- A newly assigned teacher must exist and have an active teacher profile.
- Switching a one-on-one student to batch clears the permanent teacher assignment.
- Switching a batch student to one-on-one leaves the assignment empty until admin assigns one.
- Deactivating an assigned teacher clears all permanent student assignments to that teacher.
- Deleting a teacher sets matching permanent student assignments to null.

### `packages`

Stores admin-configured purchasable course packages.

Fields:

- `id`
- `name`
- `duration_days`
- `price_amount`
- `currency`
- `is_active`
- `created_at`
- `updated_at`

Rules:

- `duration_days` must be greater than 0.
- `price_amount` must be greater than or equal to 0.
- Price is stored as integer minor units.
- Currency defaults to `INR`.
- One month equals 30 days, so 1/2/3 month packages are 30/60/90 days.
- Packages can be deactivated with `is_active = false`.
- Packages can be voided by admin, which sets `is_active = false`.
- Voiding a package does not delete the package record.
- Package records are not payment records and do not grant access by themselves.

### `student_payments`

Stores admin-entered payment records.

Fields:

- `id`
- `student_id`
- `package_id`
- `amount_paid`
- `currency`
- `payment_method`
- `paid_at`
- `created_by_user_id`
- `notes`
- `created_at`
- `updated_at`

Allowed `payment_method` values:

- `upi`
- `cash`
- `bank_transfer`
- `other`

Rules:

- A payment must link to an existing student.
- A payment can optionally link to an existing package.
- A payment can optionally link to the user who created it.
- `amount_paid` must be greater than or equal to 0.
- Currency defaults to `INR`.
- `paid_at` is stored as a timezone-aware UTC datetime.
- Payment records can be edited by admin.
- Payment records can be hard-deleted by admin.
- Payment records do not activate students.
- Payment records do not grant access.
- Student access is handled separately through access grants.

### `student_access_grants`

Stores admin-entered access grants.

Fields:

- `id`
- `student_id`
- `package_id`
- `grant_type`
- `duration_days`
- `access_starts_at`
- `access_ends_at`
- `created_by_user_id`
- `notes`
- `created_at`
- `updated_at`

Allowed `grant_type` values:

- `package`
- `addon_days`
- `manual_adjustment`

Rules:

- An access grant must link to an existing student.
- An access grant can optionally link to an existing package.
- A package grant must include `package_id`.
- Package grants cannot use an inactive package.
- If `duration_days` is omitted and a package is linked, the package duration is used.
- If no package duration is available, `duration_days` is required.
- `duration_days` must be greater than 0.
- Access grants can optionally link to the user who created them.
- Creating an access grant updates the student's `access_starts_at` and `access_ends_at`.
- Creating an access grant does not change student status.
- Existing future access is extended by default.
- Admin can pass `extend_current_access = false` to start fresh.
- Admin can pass `access_starts_at`.
- If no custom start is provided, access starts from now.
- If access starts mid-day UTC, the next UTC date is counted as day one.
- If access starts exactly at UTC midnight, that UTC date is counted as day one.
- `access_ends_at` is stored as exclusive next-midnight UTC.

### `student_program_changes`

Stores admin-driven program switch history.

Fields:

- `id`
- `student_id`
- `old_program_type`
- `new_program_type`
- `changed_by_user_id`
- `reason`
- `created_at`
- `updated_at`

Rules:

- A program change must link to an existing student.
- A program change can optionally link to the user who made the change.
- Program switching happens immediately.
- The student's `program_type` is updated when a switch is recorded.
- No history record is created when the new program matches the current program.
- Existing package/access validity remains unchanged.
- Future bookings are cancelled when admin switches a student's program type.
- Switching a student from `batch` to `one_on_one` ends the student's active batch membership.
- Batch students can be assigned to one active batch group.
- Admin can transfer a batch student from one batch group to another.
- Batch groups optionally reference one package; new active groups require an active package.
- New batch membership and transfer require a currently valid access grant for the destination
  group's package unless admin supplies a reasoned package-access override.
- Batch transfer history is stored through membership rows.
- Batch transfer cancels future booked bookings from the old batch group.

## Student Profile APIs

Authenticated student portal APIs are under `/api/v1/student/me`. They derive the student profile
from the bearer token and expose only that student's bookings, grants, assigned-teacher available
slots, batch-day options, and student-visible booking feedback. Cancellation and rescheduling are
limited to the caller's own booking.
`GET /student/me` uses `{user, student, assigned_teacher}`. Booking rows include their class,
teacher, and batch projections; available slots include the assigned-teacher summary. Batch-day
and feedback endpoints return portal-ready arrays (not admin pagination envelopes).

Base path:

```txt
/api/v1/students
```

Endpoints:

- `GET /api/v1/students`
- `POST /api/v1/students`
- `GET /api/v1/admin/students`
- `POST /api/v1/admin/students`
- `GET /api/v1/admin/students/{student_id}`
- `PATCH /api/v1/admin/students/{student_id}`
- `GET /api/v1/students/program-changes`
- `GET /api/v1/students/program-changes?student_id={student_id}`
- `GET /api/v1/students/{student_id}`
- `PATCH /api/v1/students/{student_id}`
- `POST /api/v1/students/{student_id}/program-switch`
- `GET /api/v1/admin/students/{student_id}/payments`
- `POST /api/v1/admin/students/{student_id}/payments`
- `PATCH /api/v1/admin/students/{student_id}/payments/{payment_id}`
- `DELETE /api/v1/admin/students/{student_id}/payments/{payment_id}`
- `GET /api/v1/admin/students/{student_id}/access-grants`
- `POST /api/v1/admin/students/{student_id}/access-grants`
- `POST /api/v1/admin/students/{student_id}/program-switch`
- `POST /api/v1/admin/students/{student_id}/batch-group`
- `GET /api/v1/admin/students/{student_id}/batch-memberships`
- `GET /api/v1/students/{student_id}/batch-schedule-days`
- `PUT /api/v1/students/{student_id}/batch-schedule-days/{day_id}/selection`

`POST /api/v1/admin/students` creates the student user and linked student profile atomically.
Payments, access grants, program switching, and batch assignment are exposed through path-scoped
admin aliases that reuse existing domain services.
Admin payment update/delete aliases are path-scoped by student and do not allow moving a payment
between students.
`PATCH /api/v1/admin/students/{student_id}` updates student profile fields. If `program_type`
changes through this admin patch, the existing program switch behavior is used so history, future
booking cancellation, and batch membership cleanup still happen.

Batch students with an active membership can list upcoming UTC batch schedule days for their
group. Responses contain open session options, capacity availability, and the student's current
selection. A student can select exactly one option per batch-day parent. Selection requires active
student status, active membership, scheduled/future capacity, and access covering the option start.
The patch accepts nullable `assigned_teacher_id` for assigning, changing, or clearing the permanent
teacher of a one-on-one student. Assigning an inactive teacher or assigning any teacher to a batch
student is rejected.

Student list endpoints and program change list endpoints are paginated with `page` and `page_size`.
Admin student read endpoints return student profile data nested with linked user data. They also
return `assigned_teacher` as nested teacher and teacher-user data when a permanent teacher is
assigned; otherwise it is null.

`GET /api/v1/admin/students` supports admin-facing filters:

- `q`: searches linked user `full_name`, `email`, and `phone`.
- `status`: filters by student status.
- `program_type`: filters by `one_on_one` or `batch`.
- `access_state`: filters by raw access window state. Allowed values are `valid`, `expired`,
  `not_started`, and `none`.
- `batch_group_id`: filters by active batch group membership.
- `assigned_teacher_id`: filters by the student's permanent one-on-one teacher assignment. It
  does not include students based on teachers from class history.
- `sort_by`: sorts the full filtered database result before pagination. Allowed values are
  `created_at`, `joined_at`, `name`, `status`, `program_type`, and `access_ends_at`. `name` sorts
  by the linked user's `full_name`.
- `sort_order`: controls sort direction with `asc` or `desc`.

Admin student sorting defaults to `sort_by=created_at&sort_order=desc`. Null sort values, including
missing `access_ends_at`, are placed last in both directions. Student ID is used as a stable
secondary sort for deterministic pagination.

## Package APIs

Base path:

```txt
/api/v1/packages
```

Endpoints:

- `GET /api/v1/packages`
- `POST /api/v1/packages`
- `POST /api/v1/admin/packages`
- `GET /api/v1/packages/{package_id}`
- `GET /api/v1/admin/packages/{package_id}`
- `PATCH /api/v1/packages/{package_id}`
- `PATCH /api/v1/admin/packages/{package_id}`
- `POST /api/v1/packages/{package_id}/void`
- `POST /api/v1/admin/packages/{package_id}/void`

`GET /api/v1/packages` and `GET /api/v1/admin/packages` are paginated with `page` and
`page_size`. The admin list also supports `q`, `is_active`, `sort_by`, and `sort_order`;
supported sort fields are `created_at`, `name`, `duration_days`, `price_amount`, and `is_active`.
Admin sorting defaults to `created_at desc` and uses package ID as a deterministic tiebreaker.
`POST /api/v1/admin/packages` reuses the existing package creation behavior.
`PATCH /api/v1/admin/packages/{package_id}` reuses the existing package update behavior.
`POST /api/v1/admin/packages/{package_id}/void` reuses the existing package void behavior.

## Payment APIs

Base path:

```txt
/api/v1/student-payments
```

Endpoints:

- `GET /api/v1/student-payments`
- `GET /api/v1/student-payments?student_id={student_id}`
- `POST /api/v1/student-payments`
- `GET /api/v1/student-payments/{payment_id}`
- `PATCH /api/v1/student-payments/{payment_id}`
- `DELETE /api/v1/student-payments/{payment_id}`
- `PATCH /api/v1/admin/students/{student_id}/payments/{payment_id}`
- `DELETE /api/v1/admin/students/{student_id}/payments/{payment_id}`

Student payment list endpoints are paginated with `page` and `page_size`.
Admin payment update/delete aliases require the payment to already belong to the path
`student_id`.

## Access Grant APIs

Base path:

```txt
/api/v1/student-access-grants
```

Endpoints:

- `GET /api/v1/student-access-grants`
- `GET /api/v1/student-access-grants?student_id={student_id}`
- `POST /api/v1/student-access-grants`
- `GET /api/v1/student-access-grants/{grant_id}`

Student access grant list endpoints are paginated with `page` and `page_size`.

## Known Product Direction

Students can be one of:

- `one_on_one`
- `batch`

One-on-one students:

- Book a class based on teacher availability.
- Can book one class per day.

Batch students:

- Join one of three daily classes.
- Daily class options are configurable by admin.
- Students choose their batch class per day.
- The student booking/change window closes three hours before class start.
- Admin can manually add any student to any batch class.
- Teacher assignment for batch classes is done by admin and can be bulk assigned.

Access and package direction:

- Packages are separate records.
- One month means 30 days.
- Payments and access grants are separate records.
- Access grants do not depend on payments.
- Admin manually controls status and access.
- Access can be granted with an admin-provided start date/time.
- If no custom start is provided, access starts from now and tomorrow counts as day one.
- Future bookings are cancelled when admin switches a student's program type.
- Students whose access has expired can view history but cannot book or attend future classes.
- Changing a batch group's package does not retroactively change or revoke student access.

## Decisions Still Needed

- Whether package changes should trigger a future opt-in migration workflow for existing members.

## Deferred
