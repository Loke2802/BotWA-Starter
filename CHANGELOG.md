# Changelog

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

