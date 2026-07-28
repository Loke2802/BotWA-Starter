# PRD-002 Authentication and Users

**Date:** 2026-07-28  
**Status:** CLOSED  
**Phase:** Phase 3 Product Development  
**Branch:** `feat/prd-002-auth-users`

## Objective

Create the identity baseline for BotWA organizations:

- users belong to exactly one active organization;
- users authenticate with email and password;
- passwords are stored only as maintained-library hashes;
- authenticated users can query their identity;
- password change invalidates previous access tokens;
- users can be deactivated without physical deletion.

## Architecture

PRD-002 is implemented outside the five Core Engines.

| Layer | Files |
|---|---|
| Domain | `app/domain/user/contracts.py` |
| Application users | `app/application/users/service.py` |
| Application auth | `app/application/auth/service.py` |
| Security | `app/security/passwords.py`, `app/security/tokens.py` |
| Infrastructure | `app/infrastructure/models/user.py`, `app/infrastructure/repositories/user_repository.py` |
| API | `app/api/dependencies.py`, `app/api/routes.py` |
| Migration | `alembic/versions/20260728_0003_create_user_table.py` |

No Conversation, Business Brain, Knowledge, Automation, or Integration Engine
responsibilities were changed.

## User Model

Table name: `app_user`.

Fields:

- `id`: UUID
- `organization_id`: UUID, required FK to `organization.id`
- `email`: required, normalized lowercase, globally unique
- `password_hash`: required, never exposed by API contracts
- `first_name`: optional
- `last_name`: optional
- `status`: `active` or `inactive`
- `auth_version`: integer credential version for token invalidation
- `created_at`
- `updated_at`
- `last_login_at`
- `deactivated_at`

## Business Rules

- Email is required, normalized to lowercase, and globally unique.
- Password minimum length is 12 characters.
- Organization must exist and be active to create users.
- `organization_id` cannot be changed after creation.
- Inactive users cannot log in.
- Deactivation is idempotent at the application service level.
- There is no physical delete.
- `last_login_at` is recorded after successful login.

## Security

- Password hashing uses `argon2-cffi` (`PasswordHasher`, Argon2id default).
- Access tokens use JWT via `PyJWT`.
- JWT algorithm defaults to `HS256`.
- JWT includes `sub`, `exp`, and `auth_version`.
- Token expiration defaults to 30 minutes.
- Password change increments `auth_version` and invalidates previous tokens.
- Deactivation increments `auth_version`.
- Login errors use generic `invalid credentials` for wrong email/password.
- API responses never expose `password_hash`.

Environment variables:

- `BOTWA_AUTH_SECRET_KEY`
- `BOTWA_AUTH_ALGORITHM`
- `BOTWA_AUTH_ACCESS_TOKEN_EXPIRE_MINUTES`
- `BOTWA_AUTH_PASSWORD_MIN_LENGTH`

No real secrets are stored in the repository.

## Bootstrap

Temporary PRD-002 bootstrap:

- `POST /users` may create the first user for an active organization without authentication.
- After an organization has one user, creating more users requires an authenticated active user from the same organization.
- This avoids adding roles in PRD-002.
- PRD-003 must replace this temporary bootstrap with explicit administration/authorization.

## API

| Method | Endpoint | Auth | Result |
|---|---|---|---|
| POST | `/users` | Bootstrap or Bearer | Create user |
| GET | `/users` | Bearer | List users in actor organization |
| GET | `/users/{user_id}` | Bearer | Get visible user |
| PATCH | `/users/{user_id}` | Bearer | Update basic profile |
| POST | `/users/{user_id}/deactivate` | Bearer | Soft deactivate user |
| POST | `/auth/login` | None | Return Bearer access token |
| GET | `/auth/me` | Bearer | Return current identity |
| POST | `/auth/change-password` | Bearer | Change password and invalidate previous tokens |

Status decisions:

- Invalid credentials: `401`
- Invalid or expired token: `401`
- Missing token on protected endpoint: `401`
- Inactive user: `403`
- Organization not found: `404`
- Inactive organization: `409`
- Duplicate email: `409`
- Validation errors: `422`

## Exclusions

- OAuth social login
- SSO
- MFA
- password recovery by email
- invitations
- roles
- granular permissions
- platform admin
- billing
- dashboard
- frontend
- PRD-003

## Temporary Debt For PRD-003

- Replace bootstrap user creation with explicit admin authorization.
- Define roles/permissions before exposing user administration broadly.
- Add password recovery/invitation flows in a future PRD.
- Add production secret management outside repository files.

## Closure Criteria

| Criterion | Result |
|---|---|
| User model | PASS |
| Organization association | PASS |
| Argon2 password hashing | PASS |
| JWT access token | PASS |
| `/auth/me` | PASS |
| Change password | PASS |
| Previous-token invalidation | PASS |
| Inactive-user login rejection | PASS |
| PostgreSQL persistence | PASS |
| Alembic upgrade/downgrade/upgrade | PASS |
| Docker smoke | PASS |
| Quality gates | PASS |
| PRD-003 not started | PASS |

## Decision

**PRD-002 CLOSED**
