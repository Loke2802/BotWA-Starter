# PRD-005 Business Configuration

**Date:** 2026-07-29  
**Status:** CLOSED  
**Phase:** Phase 3 Product Development  
**Branch:** `feat/prd-005-business-configuration`

## Objective

Allow each bot to own one tenant-scoped business configuration managed by its
organization.

The configuration answers:

- what company the bot represents;
- business hours and timezone;
- offered services;
- accepted payment methods;
- basic policies;
- service instructions;
- when human handoff should be requested.

## Architecture

PRD-005 is implemented outside the five Core Engines.

| Layer | Files |
|---|---|
| Domain | `app/domain/business_configuration/contracts.py`, `app/domain/access/contracts.py` |
| Application | `app/application/business_configuration/service.py` |
| Infrastructure | `app/infrastructure/models/business_configuration.py`, `app/infrastructure/repositories/business_configuration_repository.py` |
| API | `app/api/dependencies.py`, `app/api/routes.py` |
| Migration | `alembic/versions/20260728_0006_create_business_configuration_table.py` |

No Core Engine responsibilities, Blueprints, or ADRs were changed.

## Business Configuration Contract

| Field | Notes |
|---|---|
| `id` | UUID |
| `bot_id` | Required Bot owner, unique |
| `business_name` | Required commercial name |
| `description` | Required business description |
| `phone` | Optional |
| `email` | Optional, validated |
| `website` | Optional, validated HTTP(S) URL |
| `address` | Optional |
| `timezone` | Valid IANA timezone through `zoneinfo` |
| `business_hours` | Structured days with enabled/open/close |
| `services` | Validated structured service list |
| `payment_methods` | Non-empty string list without duplicates |
| `policies` | Validated structured policy list |
| `service_instructions` | Required operating instructions |
| `handoff_enabled` | Boolean |
| `handoff_message` | Optional |
| `handoff_keywords` | Optional non-empty string list without duplicates |
| `handoff_outside_business_hours` | Boolean |
| `status` | `configured` |
| `created_at`, `updated_at` | Audit timestamps |

## Endpoints

- `POST /bots/{bot_id}/business-configuration`
- `GET /bots/{bot_id}/business-configuration`
- `PATCH /bots/{bot_id}/business-configuration`

## Permissions

New permissions:

- `business_configuration.create`
- `business_configuration.read`
- `business_configuration.update`

Role matrix:

| Role | Business Configuration permissions |
|---|---|
| `platform_admin` | all permissions across organizations |
| `organization_owner` | create/read/update inside its organization |
| `organization_admin` | create/read/update inside its organization |
| `operator` | read |
| `viewer` | read |

## Rules

- Bot must exist.
- Bot organization is the source of tenant scope.
- Non-platform users cannot access another organization's bot configuration.
- `platform_admin` can operate cross-organization.
- A bot can have only one configuration in this PRD.
- Duplicate configuration creation returns `409`.
- `bot_id` cannot be changed.
- Bots from inactive organizations cannot be modified.
- Inactive bots can retain and expose their configuration.
- No physical delete is exposed.

## Structured Validation

Business hours:

- represented by seven days;
- enabled days require `open_time` and `close_time`;
- time format is `HH:MM`;
- `open_time` must be before `close_time`;
- closed days can omit times.

Services:

- `name`;
- optional `description`;
- `active`;
- optional non-negative `price`;
- optional ISO-style `currency`;
- optional positive `duration_minutes`.

Policies:

- `name`;
- `description`;
- `active`.

Handoff:

- `handoff_enabled`;
- optional `handoff_message`;
- optional `handoff_keywords`;
- optional `handoff_outside_business_hours`.

## Migration

Alembic revision:

- `20260728_0006_create_business_configuration_table.py`

Database objects:

- table `business_configuration`;
- foreign key `fk_business_configuration_bot_id_bot`;
- primary key `pk_business_configuration`;
- unique constraint `uq_business_configuration_bot_id`;
- index `ix_business_configuration_bot_id`.

## Exclusions

- PRD-006.
- Knowledge Sources or document management.
- Complex service catalog.
- Inventory.
- Reservations.
- CRM integration.
- WhatsApp connection or live validation.
- Automation execution.
- Frontend/dashboard.
- Billing.

## Closure Criteria

| Criterion | Result |
|---|---|
| Business Configuration domain contract | PASS |
| Business Configuration application service | PASS |
| PostgreSQL persistence | PASS |
| Alembic upgrade/downgrade/upgrade | PASS |
| API endpoints | PASS |
| RBAC permissions | PASS |
| Multi-tenancy | PASS |
| Structured validation | PASS |
| Inactive organization write blocking | PASS |
| Inactive bot read preservation | PASS |
| Docker smoke | PASS |
| Quality gates | PASS |
| PRD-006 not started | PASS |

## Decision

**PRD-005 CLOSED**
