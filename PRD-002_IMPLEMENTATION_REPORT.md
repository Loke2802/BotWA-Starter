# PRD-002 Authentication and Users Implementation Report

**Date:** 2026-07-28  
**Branch:** `feat/prd-002-auth-users`  
**Status:** PRD-002 CLOSED

## Summary

Implemented the BotWA identity baseline for Phase 3 without modifying Core Engine
responsibilities or starting PRD-003.

## Added

- User domain contracts.
- User application service.
- Auth application service.
- Argon2id password hashing via `argon2-cffi`.
- JWT access tokens via `PyJWT`.
- Reusable FastAPI Bearer dependency.
- PostgreSQL-backed `app_user` ORM model and repository.
- Alembic migration `20260728_0003_create_user_table.py`.
- Users and auth endpoints.
- Unit, endpoint, auth, migration, and PRD-001 regression tests.

## Architecture

PRD-002 follows the PRD-001 product/admin layering:

- Domain: pure Pydantic contracts.
- Application: use cases and business rules.
- Security: password hashing and JWT token services.
- Infrastructure: SQLAlchemy model and repository.
- API: thin route handlers and dependency injection.

No Core Engines, Blueprints, or ADRs were changed.

## Security Decisions

- Password hashing: Argon2id through maintained `argon2-cffi`.
- Access tokens: JWT HS256 through maintained `PyJWT`.
- Expiration: configurable, default 30 minutes.
- Token invalidation: `auth_version` included in JWT and stored on `app_user`.
- Password change increments `auth_version`.
- Deactivation increments `auth_version`.
- Password hashes and internal security fields are not exposed by API responses.
- Login failures for wrong email/password use generic `invalid credentials`.

## Bootstrap

Temporary bootstrap allows unauthenticated creation of the first user for an active
organization. Additional users require an authenticated active user from the same
organization. PRD-003 must replace this with explicit roles/authorization.

## Endpoints

- `POST /users`
- `GET /users`
- `GET /users/{user_id}`
- `PATCH /users/{user_id}`
- `POST /users/{user_id}/deactivate`
- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/change-password`

## Migration

Created Alembic revision:

- `20260728_0003_create_user_table.py`

Validated in Docker/PostgreSQL:

- `alembic upgrade head`
- `alembic downgrade 20260728_0002`
- `alembic upgrade head`
- `alembic heads` -> `20260728_0003 (head)`

## Tests

Added:

- `tests/test_user_contracts.py`
- `tests/test_user_service.py`
- `tests/test_auth_service.py`
- `tests/test_user_endpoints.py`
- `tests/test_user_migration.py`

Coverage includes:

- user creation;
- email normalization;
- invalid email;
- duplicate email;
- missing/inactive organization;
- weak password;
- hash not equal to password;
- password hash not exposed;
- successful login;
- wrong password;
- inactive login;
- valid, altered, expired, and invalidated token behavior;
- `/auth/me`;
- password change;
- profile update;
- rejected `organization_id` change;
- deactivation;
- service-level idempotent deactivation;
- migration contract;
- PRD-001 organization regression;
- full Core regression.

## Docker/PostgreSQL Evidence

Commands/results:

- `docker version`: daemon available after Docker Desktop startup, ServerVersion `29.6.1`.
- `docker compose up -d --build`: image built, PostgreSQL healthy, API started.
- `GET /health`: `status=ok`.
- `GET /version`: `BotWA Starter`, `v1`, `local`.
- `alembic upgrade head`: upgraded `20260728_0002 -> 20260728_0003`.
- `alembic downgrade 20260728_0002`: downgraded `20260728_0003 -> 20260728_0002`.
- `alembic upgrade head`: upgraded again to `20260728_0003`.
- `psql \dt`: `app_user` table present.

Smoke flow:

- Created organization `e1ca2d44-6b8c-4f24-9ca1-e86067fcd771`.
- Created user `345a625d-5117-4176-91c3-4ccfbea9088a`.
- `password_hash_exposed=false`.
- Login returned `token_type=bearer`.
- `/auth/me` returned `owner-20260728141036@example.com`.
- Password change succeeded.
- Old password login returned `401`.
- New password login succeeded.
- Deactivation returned `inactive`.
- Inactive login returned `403`.
- Direct PostgreSQL confirmed `hash_not_plaintext=t`, `auth_version=3`,
  `has_last_login=t`, `has_deactivated_at=t`.
- API restart preserved the user row with `status=inactive`, `auth_version=3`.

## Quality Gates

| Gate | Result |
|---|---|
| `pytest` | 513 passed, 1 warning |
| `ruff check app tests` | All checks passed |
| `black --check app tests` | 199 files would be left unchanged |
| `mypy app tests` | Success: no issues found in 199 source files |

## Security Review

| Check | Result |
|---|---|
| No real secrets committed | PASS |
| Passwords are not logged | PASS |
| Tokens are not logged by application code | PASS |
| Login credential errors are generic | PASS |
| JWT validates `exp` | PASS |
| JWT validates signature | PASS |
| JWT includes user identifier | PASS |
| JWT includes credential version | PASS |
| Password change invalidates previous tokens | PASS |
| Hashing uses maintained library salt behavior | PASS |
| API does not expose internal security fields | PASS |

## Risks

- PRD-003 must add explicit roles/authorization and replace temporary bootstrap.
- Production secret management must provide a strong `BOTWA_AUTH_SECRET_KEY`.
- WhatsApp real/live remains blocked by external credentials, unrelated to PRD-002.

## Decision

**PRD-002 CLOSED**
