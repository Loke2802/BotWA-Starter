# PRD-004 Bot Management

**Date:** 2026-07-28  
**Status:** CLOSED  
**Phase:** Phase 3 Product Development  
**Branch:** `feat/prd-004-bot-management`

## Objective

Implement tenant-scoped bot management on top of the existing Core platform:

- create bots for active organizations;
- list and read bots according to organization scope;
- update bot metadata without changing ownership;
- activate and deactivate bots idempotently;
- extend RBAC with bot permissions;
- persist bots in PostgreSQL.

## Architecture

PRD-004 is implemented outside the five Core Engines.

| Layer | Files |
|---|---|
| Domain | `app/domain/bot/contracts.py`, `app/domain/access/contracts.py` |
| Application | `app/application/bots/service.py` |
| Infrastructure | `app/infrastructure/models/bot.py`, `app/infrastructure/repositories/bot_repository.py` |
| API | `app/api/dependencies.py`, `app/api/routes.py` |
| Migration | `alembic/versions/20260728_0005_create_bot_table.py` |

No Core Engine responsibilities, Blueprints, or ADRs were changed.

## Bot Contract

| Field | Notes |
|---|---|
| `id` | UUID |
| `organization_id` | Required owner organization |
| `name` | Required display name |
| `slug` | Normalized slug, unique inside one organization |
| `description` | Optional |
| `status` | `active` or `inactive` |
| `default_language` | BCP-style short language value, default `es` |
| `timezone` | Validated with Python `zoneinfo` |
| `welcome_message` | Optional |
| `away_message` | Optional |
| `settings` | Optional JSON object |
| `created_at`, `updated_at` | Audit timestamps |
| `activated_at`, `deactivated_at` | Lifecycle timestamps |

## Endpoints

- `POST /bots`
- `GET /bots`
- `GET /bots/{bot_id}`
- `PATCH /bots/{bot_id}`
- `POST /bots/{bot_id}/activate`
- `POST /bots/{bot_id}/deactivate`

## Permissions

New permissions:

- `bots.create`
- `bots.read`
- `bots.update`
- `bots.activate`
- `bots.deactivate`

Role matrix:

| Role | Bot permissions |
|---|---|
| `platform_admin` | all bot permissions across organizations |
| `organization_owner` | all bot permissions inside its organization |
| `organization_admin` | all bot permissions inside its organization |
| `operator` | `bots.read` |
| `viewer` | `bots.read` |

## Multi-Tenancy

- Non-platform users derive organization scope from the authenticated user.
- Non-platform users cannot read, update, activate, or deactivate bots from another organization.
- Non-platform list returns only bots from the actor organization.
- `platform_admin` can list globally and create bots for an explicit organization.
- `slug` is unique per organization, not globally.
- The same slug is allowed in different organizations.

## Lifecycle Rules

- New bots start `inactive`.
- Activation requires the owning organization to be active.
- Deactivation is idempotent.
- Activation is idempotent.
- Inactive bots remain readable.
- Physical delete is not supported.
- `organization_id` cannot be changed through update.
- Inactive organizations can be read, but bot writes are blocked.

## Migration

Alembic revision:

- `20260728_0005_create_bot_table.py`

Database objects:

- table `bot`;
- foreign key `fk_bot_organization_id_organization`;
- primary key `pk_bot`;
- unique constraint `uq_bot_organization_id_slug`;
- index `ix_bot_organization_id`.

## Exclusions

- PRD-005.
- Bot runtime assignment to WhatsApp numbers.
- Bot-specific knowledge bases.
- Bot-specific business configuration.
- Frontend/dashboard.
- Billing.
- Onboarding.
- WhatsApp real/live credentials.

## Closure Criteria

| Criterion | Result |
|---|---|
| Bot domain contract | PASS |
| Bot application service | PASS |
| PostgreSQL persistence | PASS |
| Alembic upgrade/downgrade/upgrade | PASS |
| Bot API endpoints | PASS |
| RBAC permissions | PASS |
| Multi-tenancy | PASS |
| Slug unique per tenant | PASS |
| Activation/deactivation idempotency | PASS |
| Inactive organization write blocking | PASS |
| Docker smoke | PASS |
| Quality gates | PASS |
| PRD-005 not started | PASS |

## Decision

**PRD-004 CLOSED**
