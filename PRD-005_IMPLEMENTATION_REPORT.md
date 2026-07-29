# PRD-005 Business Configuration Implementation Report

**Date:** 2026-07-29  
**Branch:** `feat/prd-005-business-configuration`  
**Status:** PRD-005 CLOSED

## Summary

Implemented Business Configuration for Phase 3 without modifying Core Engine
responsibilities or starting PRD-006.

## Added

- Business Configuration domain contracts and validation helpers.
- Structured `BusinessHours`, `BusinessService`, and `BusinessPolicy` contracts.
- Business Configuration application service with tenant-scoped authorization.
- PostgreSQL-backed `business_configuration` ORM model and repository.
- Alembic migration `20260728_0006_create_business_configuration_table.py`.
- API endpoints for create, read, and update under `/bots/{bot_id}`.
- Business Configuration permissions in the central RBAC matrix.
- Unit, API, migration, multi-tenancy, RBAC, validation, and regression tests.

## Quality Gates

| Gate | Result |
|---|---|
| `pytest` | 545 passed, 1 warning |
| `ruff check app tests` | All checks passed |
| `black --check app tests` | 224 files would be left unchanged |
| `mypy app tests` | Success: no issues found in 224 source files |

## Docker/PostgreSQL Evidence

- `docker version`: client `29.6.1`, server `29.6.1`.
- `docker compose up -d --build`: image built, PostgreSQL healthy, API started.
- Final `docker compose ps`: API up on `0.0.0.0:8000`; PostgreSQL healthy on `0.0.0.0:5432`.
- `GET /health`: `status=ok`.
- `GET /version`: `BotWA Starter`, `v1`, `local`.
- `alembic current` before PRD-005 upgrade: `20260728_0005`.
- `alembic upgrade head`: upgraded `20260728_0005 -> 20260728_0006`.
- `alembic downgrade 20260728_0005`: downgraded `20260728_0006 -> 20260728_0005`.
- `alembic upgrade head`: upgraded again to `20260728_0006`.
- `alembic current`: `20260728_0006 (head)`.
- PostgreSQL confirmed table `business_configuration`.
- PostgreSQL confirmed constraints `pk_business_configuration`, `fk_business_configuration_bot_id_bot`, and `uq_business_configuration_bot_id`.

Smoke flow:

- `GET /health`: `200`.
- `GET /version`: `200`.
- `POST /messages` greeting: `accepted`.
- `POST /messages` knowledge query: `accepted`.
- Created organizations `7ad712b3-eff8-4d22-a56c-9685acba4ad6` and `1aa1bfd9-5523-4efb-b6ae-8262f9f81b02`.
- Created owners for both organizations; both received `organization_owner`.
- Created `organization_admin`, `viewer`, `operator`, and DB-promoted `platform_admin`.
- Created bots `c438cf73-503a-40b1-992b-bb7245b7dbf1` and `fd7a68ae-6866-4fd3-a083-89030ad41717`.
- Admin created configuration for bot A.
- Owner read and updated configuration for bot A.
- Duplicate configuration returned `409`.
- Missing bot returned `404`.
- Invalid email returned `422`.
- Viewer read returned `200`.
- Viewer update returned `403`.
- Operator create returned `403`.
- Cross-tenant read returned `403`.
- Cross-tenant update returned `403`.
- Platform admin created and read configuration for bot B.
- Inactive bot configuration read returned `200`.
- Inactive organization update returned `409`.
- Direct PostgreSQL query returned 2 business configurations for the smoke bots.
- API restart preserved configuration records; DB count remained `2`, read after restart returned `Smoke Business Updated`.

Persisted smoke rows:

| bot_id | business_name | timezone | handoff_enabled |
|---|---|---|---|
| `c438cf73-503a-40b1-992b-bb7245b7dbf1` | `Smoke Business Updated` | `America/Bogota` | false |
| `fd7a68ae-6866-4fd3-a083-89030ad41717` | `Smoke Business` | `America/Lima` | true |

## Security Review

| Check | Result |
|---|---|
| Tenant-scoped bot validation | PASS |
| Cross-tenant configuration read blocked | PASS |
| Cross-tenant configuration update blocked | PASS |
| Platform admin cross-organization access | PASS |
| Viewer/operator write denial | PASS |
| Owner/admin write access | PASS |
| `bot_id` immutable | PASS |
| Inactive organization writes blocked | PASS |
| Inactive bot read preservation | PASS |
| PRD-006 not started | PASS |

## Risks

- Future PRDs must define how Core Engines consume Business Configuration through an explicit adapter/provider.
- Future PRDs must define Knowledge Sources and bot-specific Knowledge behavior.
- Future PRDs must define WhatsApp channel assignment per bot.
- WhatsApp real/live validation remains blocked by external credentials.

## Decision

**PRD-005 CLOSED**
