# PRD-003 Roles and Permissions

**Date:** 2026-07-28  
**Status:** CLOSED  
**Phase:** Phase 3 Product Development  
**Branch:** `feat/prd-003-roles-permissions`

## Objective

Implement basic authorization for BotWA users inside organizations:

- identify the user's role;
- derive effective permissions from a central matrix;
- decide whether a user can execute an action;
- prevent cross-organization access except for `platform_admin`;
- replace the temporary PRD-002 bootstrap debt.

## Architecture

PRD-003 is implemented outside the five Core Engines.

| Layer | Files |
|---|---|
| Domain | `app/domain/access/contracts.py`, `app/domain/user/contracts.py` |
| Application | `app/application/access/service.py`, `app/application/users/service.py` |
| Security | `app/security/authorization.py` |
| Infrastructure | `app/infrastructure/models/user.py`, `app/infrastructure/repositories/user_repository.py` |
| API | `app/api/dependencies.py`, `app/api/routes.py` |
| Migration | `alembic/versions/20260728_0004_add_user_roles.py` |

No Core Engine responsibilities, Blueprints, or ADRs were changed.

## Roles

- `platform_admin`
- `organization_owner`
- `organization_admin`
- `operator`
- `viewer`

## Permissions

- `organizations.read`
- `organizations.update`
- `users.create`
- `users.read`
- `users.update`
- `users.deactivate`
- `roles.read`
- `roles.assign`
- `platform.organizations.read`
- `platform.organizations.manage`

## Role Matrix

| Role | Permissions |
|---|---|
| `platform_admin` | all defined permissions; multi-organization access |
| `organization_owner` | organization read/update, user create/read/update/deactivate, role read/assign inside its organization except platform admin |
| `organization_admin` | organization read, user create/read/update/deactivate, role read/assign only admin/operator/viewer |
| `operator` | organization read, user read |
| `viewer` | organization read |

## Bootstrap

PRD-003 absorbs the temporary PRD-002 bootstrap:

- first user of an active organization can be created without authentication;
- first user receives `organization_owner`;
- later users require authentication and `users.create`;
- later users default to `viewer`;
- explicit role assignment during creation requires `roles.assign`;
- `platform_admin` can act across organizations.

## Assignment Rules

- `viewer` cannot assign roles.
- `operator` cannot assign roles.
- `organization_admin` cannot assign `platform_admin` or `organization_owner`.
- `organization_owner` can assign organization roles except `platform_admin`.
- `platform_admin` can assign any role across organizations.
- Users cannot change their own role.
- Downgrading the last active `organization_owner` is blocked.
- Deactivating the last active `organization_owner` is blocked.

## Protected Endpoints

Organizations:

- `GET /organizations`
- `GET /organizations/{organization_id}`
- `PATCH /organizations/{organization_id}`
- `POST /organizations/{organization_id}/deactivate`

Users:

- `POST /users`
- `GET /users`
- `GET /users/{user_id}`
- `PATCH /users/{user_id}`
- `POST /users/{user_id}/deactivate`

Auth endpoints remain stable:

- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/change-password`

## New Endpoints

- `GET /roles`
- `GET /permissions/me`
- `PATCH /users/{user_id}/role`

## Multi-Tenancy

- Users can only view/administer their own organization.
- `platform_admin` bypasses organization scope intentionally.
- List endpoints filter by tenant unless actor is `platform_admin`.
- Cross-tenant organization update returns `403`.
- Cross-tenant user access returns `403`.
- Authorization checks read the current user state from the database on each token validation, so role changes take effect immediately.

## Migration

Alembic revision:

- `20260728_0004_add_user_roles.py`

Backfill:

- adds non-null `role` to `app_user`;
- default is `viewer`;
- for existing users, first user per organization by `created_at`, `id` becomes `organization_owner`;
- remaining users become `viewer`;
- downgrade drops the `role` column.

## Exclusions

- custom persisted roles;
- granular resource-level policy engine;
- billing;
- dashboard;
- frontend;
- onboarding;
- MFA;
- OAuth;
- SSO;
- PRD-004.

## Closure Criteria

| Criterion | Result |
|---|---|
| Roles implemented | PASS |
| Central permission matrix | PASS |
| Protected endpoints | PASS |
| Role assignment | PASS |
| Multi-tenancy | PASS |
| Last owner protection | PASS |
| PRD-002 bootstrap replaced | PASS |
| PostgreSQL persistence | PASS |
| Alembic upgrade/downgrade/upgrade | PASS |
| Docker smoke | PASS |
| Quality gates | PASS |
| PRD-004 not started | PASS |

## Decision

**PRD-003 CLOSED**
