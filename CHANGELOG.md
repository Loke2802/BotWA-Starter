# Changelog

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
