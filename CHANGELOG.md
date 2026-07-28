# Changelog

## PRD-004 Bot Management - 2026-07-28

### Added

- Bot domain contracts and validation helpers.
- PostgreSQL-backed `bot` ORM model and repository.
- Alembic migration `20260728_0005_create_bot_table.py`.
- Bot API endpoints for create, list, read, update, activate, and deactivate.
- Bot permissions in the central RBAC matrix.
- Tests for bot contracts, API behavior, migration metadata, RBAC, multi-tenancy, and PRD regressions.

### Fixed

- Closed DB sessions for FastAPI service dependencies after each request, fixing SQLAlchemy pool exhaustion found during Docker smoke validation.

### Validated

- Docker Compose API/PostgreSQL runtime.
- Alembic upgrade/downgrade/upgrade for `20260728_0005`.
- Direct PostgreSQL bot persistence.
- Bot persistence after API restart.
- Tenant-scoped list/read/update behavior.
- Platform-admin global bot access.
- Slug uniqueness within tenant and same-slug allowance across tenants.
- Idempotent activation/deactivation.
- Inactive organization write blocking.
- Core regression quality gates.

### Not Included

- PRD-005, bot-to-WhatsApp-number routing, bot-specific Knowledge configuration, bot-specific Business configuration, billing, dashboard, frontend, onboarding, MFA, OAuth, SSO.

## PRD-003 Roles and Permissions - 2026-07-28

### Added

- Central roles and permissions domain.
- Role-permission matrix and reusable authorization helpers.
- `role` on User contracts and `app_user`.
- Alembic migration `20260728_0004_add_user_roles.py`.
- Protected Organizations and Users endpoints.
- Role and effective-permission endpoints.
- Tests for RBAC, multi-tenancy, role assignment, last-owner protection, and PRD-001/PRD-002 regressions.

### Validated

- Docker Compose API/PostgreSQL runtime.
- Alembic upgrade/downgrade/upgrade for `20260728_0004`.
- Direct PostgreSQL role persistence.
- Cross-tenant denial and platform-admin global access.
- Immediate permission effect after role changes.
- Core regression quality gates.

### Not Included

- PRD-004, custom roles, billing, dashboard, frontend, onboarding, MFA, OAuth, SSO.

## PRD-002 Authentication and Users - 2026-07-28

### Added

- User domain contracts and application service.
- Authentication application service.
- Argon2id password hashing through `argon2-cffi`.
- JWT access tokens through `PyJWT`.
- Reusable Bearer authentication dependency for FastAPI.
- PostgreSQL-backed `app_user` ORM model and repository.
- Alembic migration `20260728_0003_create_user_table.py`.
- Users and auth API endpoints.
- Unit, endpoint, auth, migration, and PRD-001 regression tests.

### Validated

- Docker Compose API/PostgreSQL runtime.
- Alembic upgrade/downgrade/upgrade for `20260728_0003`.
- Direct PostgreSQL persistence for users.
- Password hash is not plaintext.
- Login, `/auth/me`, password change, token invalidation, deactivation, and inactive-login rejection.
- API persistence after restart.
- Core regression quality gates.

### Not Included

- PRD-003, roles, granular permissions, invitations, password recovery, MFA, OAuth, SSO, billing, dashboard, frontend.

## PRD-001 Organizations - 2026-07-28

### Added

- Organization domain contracts and application service.
- PostgreSQL-backed Organization ORM model and repository.
- Alembic migration `20260728_0002_create_organization_table.py`.
- Organization API endpoints for create, list, get, update, and deactivate.
- Unit, endpoint, migration, and vertical-slice regression tests.

### Validated

- Docker Compose API/PostgreSQL runtime.
- Alembic upgrade/downgrade/upgrade for the new migration.
- PostgreSQL direct persistence and unique slug constraint.
- API persistence after restart.
- Core regression quality gates.

### Not Included

- Authentication, users, roles, billing, dashboard, frontend, PRD-002.

## core-v1.0.0 - 2026-07-28

### Status

- Closed Phase 2 as `Core v1.0.0 - Phase 2 Closed`.
- Prepared Phase 3 documentation without implementing Product Development features.

### Validated

- 470 tests passing.
- Ruff clean.
- Black clean.
- Mypy clean.
- Docker Compose build/start for API and PostgreSQL.
- Alembic migrations through `20260728_0001`.
- DB-backed conversation/message/state persistence.
- Persistence after API restart.
- Docker smoke tests for health, version, greeting, knowledge, support, and unknown flows.
- Integration Engine controlled errors/timeouts/retry tests inside Docker.

### Fixed

- Added missing Automation/Integration Alembic migration.
- Flushed persisted conversation creation before DB-backed state transitions.
- Declared `pytest-asyncio` in development dependencies for container test parity.

### Blocked

- WhatsApp real/live validation remains blocked pending external credentials or sandbox access.
