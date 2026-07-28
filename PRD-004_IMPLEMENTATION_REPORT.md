# PRD-004 Bot Management Implementation Report

**Date:** 2026-07-28  
**Branch:** `feat/prd-004-bot-management`  
**Status:** PRD-004 CLOSED

## Summary

Implemented Bot Management for Phase 3 without modifying Core Engine responsibilities
or starting PRD-005.

## Added

- Bot domain contracts and validation helpers.
- Bot application service with tenant-scoped authorization.
- PostgreSQL-backed `bot` ORM model and repository.
- Alembic migration `20260728_0005_create_bot_table.py`.
- Bot API endpoints for create, list, read, update, activate, and deactivate.
- Bot permissions in the central RBAC matrix.
- Unit, API, migration, multi-tenancy, RBAC, and regression tests.
- Runtime DB session lifecycle fix discovered during Docker validation.
- `tzdata` runtime dependency for `zoneinfo` portability in Windows/container runtimes.

## Quality Gates

| Gate | Result |
|---|---|
| `pytest` | 532 passed, 1 warning |
| `ruff check app tests` | All checks passed |
| `black --check app tests` | 215 files would be left unchanged |
| `mypy app tests` | Success: no issues found in 215 source files |

## Docker/PostgreSQL Evidence

- `docker version`: Docker Desktop `4.82.0`, engine `29.6.1`.
- `docker compose up -d --build api`: image built, PostgreSQL healthy, API started.
- Final `docker compose ps`: API up on `0.0.0.0:8000`; PostgreSQL healthy on `0.0.0.0:5432`.
- `GET /health`: `status=ok`.
- `GET /version`: `BotWA Starter`, `v1`, `local`.
- `alembic heads`: `20260728_0005 (head)`.
- `alembic current` before PRD-004 upgrade: `20260728_0004`.
- `alembic upgrade head`: upgraded `20260728_0004 -> 20260728_0005`.
- `alembic downgrade 20260728_0004`: downgraded `20260728_0005 -> 20260728_0004`.
- `alembic upgrade head`: upgraded again to `20260728_0005`.
- PostgreSQL confirmed table `bot`.
- PostgreSQL confirmed constraints `pk_bot`, `fk_bot_organization_id_organization`, and `uq_bot_organization_id_slug`.

Smoke flow:

- `GET /health`: `200`.
- `GET /version`: `200`.
- `POST /messages` greeting: `accepted`.
- `POST /messages` knowledge query: `accepted`.
- `POST /messages` support: `accepted`.
- `POST /messages` unknown: `rejected`.
- `POST /messages` invalid empty content: `422`.
- Created organizations `facce94e-bcb2-412d-b111-cad823bfabe1` and `5b2138da-a115-4877-9726-f1c2b486b382`.
- Created owners for both organizations; both received `organization_owner`.
- Created `viewer`, `operator`, and a DB-promoted `platform_admin`.
- Created bots in both organizations.
- Duplicate slug inside one organization returned `409`.
- Same slug in another organization returned `201`.
- Tenant list for owner A returned `total=1`.
- Platform admin list returned `total=5`.
- Cross-tenant read returned `403`.
- Cross-tenant update returned `403`.
- Viewer read returned `200`.
- Viewer update returned `403`.
- Operator create returned `403`.
- Bot update returned slug `updated-bot`.
- Activate twice returned `200`.
- Deactivate twice returned `200`.
- Inactive organization create returned `409`.
- Inactive organization bot activation returned `409`.
- Direct PostgreSQL query returned 3 smoke bots for the two smoke organizations.
- API restart preserved bot records; DB count remained `3`, read after restart returned `inactive`.

Persisted smoke rows:

| organization_id | slug | status |
|---|---|---|
| `5b2138da-a115-4877-9726-f1c2b486b382` | `platform-1785274124` | inactive |
| `5b2138da-a115-4877-9726-f1c2b486b382` | `shared` | inactive |
| `facce94e-bcb2-412d-b111-cad823bfabe1` | `updated-bot` | inactive |

## Defect Found During Validation

| Defect | Result |
|---|---|
| SQLAlchemy sessions opened by FastAPI providers were not closed per request, exhausting the Docker runtime pool under smoke traffic. | Fixed by converting DB-backed service providers into generator dependencies that close sessions after request completion. |

## Security Review

| Check | Result |
|---|---|
| Tenant-scoped list | PASS |
| Cross-tenant bot read blocked | PASS |
| Cross-tenant bot update blocked | PASS |
| Platform admin cross-organization access | PASS |
| Viewer/operator write denial | PASS |
| Slug unique only within tenant | PASS |
| Organization ownership immutable | PASS |
| Inactive organization writes blocked | PASS |
| PRD-005 not started | PASS |

## Risks

- Future PRDs must define how bots map to WhatsApp phone numbers and runtime routing.
- Future PRDs must define bot-specific Knowledge and Business configuration if required.
- `platform_admin` bootstrap remains operational and is not exposed as public self-service.
- WhatsApp real/live validation remains blocked by external credentials.

## Decision

**PRD-004 CLOSED**
