# Users Domain

## Purpose

The users domain stores the base person/account record used by all portals, including email/password
authentication identity and role information.

## Implemented Model

Table: `users`

Fields:

- `id`
- `full_name`
- `email`
- `phone`
- `role`
- `is_active`
- `created_at`
- `updated_at`

## Roles

Allowed `role` values:

- `admin`
- `student`
- `teacher`
- `lead_manager`

## Rules

- `email` is unique.
- `phone` is optional.
- `is_active` means the person/account is enabled globally.
- Email/password authentication is implemented for teacher invitations and existing accounts.
- Roles remain CP Hub-owned; `auth_provider_subject` is reserved for a future Google OIDC linkage.
- Passwords are Argon2 hashes and never returned by the API.
- A 15-minute bearer access JWT is returned by login/refresh. A 14-day opaque refresh token is
  stored only as a hashed database value and sent in the `cp_hub_refresh` HttpOnly cookie.
- `POST /api/v1/auth/refresh` rotates the refresh token; `POST /api/v1/auth/logout` revokes it.
- Password reset requests always return an enumeration-safe accepted response; active accounts receive a
  Resend reset link (or local-development log fallback).
- All legacy business routers are admin-only except lead-management routes, which allow admins and
  lead managers. New portal routes are self-scoped and do not accept arbitrary student or teacher
  identifiers.
- User-management APIs require an authenticated admin.

## APIs

Authentication endpoints are under `/api/v1/auth`: `POST /login`, `POST /refresh`, `POST /logout`,
`GET /me`, `POST /password/reset-request`, `POST /password/reset`, and `POST /password/setup`.
`/me`, login, and refresh return both `teacher_id` and `student_id` when the signed-in user has the
corresponding profile.

Base path:

```txt
/api/v1/users
```

Endpoints:

- `GET /api/v1/users`
- `POST /api/v1/users`
- `GET /api/v1/users/{user_id}`
- `PATCH /api/v1/admin/users/{user_id}`

`GET /api/v1/users` is paginated with `page` and `page_size` and returns:

```txt
{
  "items": [UserRead],
  "total": 0,
  "page": 1,
  "page_size": 25
}
```

Admin orchestration endpoints can also create users as part of a larger workflow:

- `POST /api/v1/admin/teachers` creates a teacher user plus teacher profile.
- `POST /api/v1/admin/students` creates a student user plus student profile.
- `PATCH /api/v1/admin/users/{user_id}` updates base account fields.

Admin user/account update rules:

- Admin can update `full_name`, `email`, `phone`, and `is_active`.
- Admin cannot update `role`.
- `email` remains unique.
- `full_name`, `email`, and `is_active` cannot be set to `null`.
- `phone` can be set to `null`.

## Files

- `app/modules/users/models.py`
- `app/modules/users/schemas.py`
- `app/modules/users/service.py`
- `app/modules/users/routes.py`

## Migration

- `alembic/versions/20260719_0001_create_users_table.py`

## Deferred

- Google OIDC linkage and external identity-provider account linking.
- Delete user APIs.
- Audit fields such as `created_by_user_id`.
