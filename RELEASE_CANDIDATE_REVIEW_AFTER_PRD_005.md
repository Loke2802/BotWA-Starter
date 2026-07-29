# Release Candidate Review After PRD-005

**Review date:** 2026-07-29  
**Base branch:** `master`  
**Review branch:** `chore/release-candidate-review-after-prd-005`  
**Decision:** `RELEASE CANDIDATE APPROVED WITH NON-BLOCKING DEBT`

## Scope and Guardrails

This review covers Core v1.0.0 and Phase 3 increments PRD-001 through PRD-005.
No product feature, Core Engine responsibility, Blueprint, ADR, migration, or public
contract was changed. PRD-006 remains:

- `NOT STARTED`
- `SCOPE NOT DEFINED`
- `REQUIRES CTO APPROVAL`

The official primary branch remains `master`; `main` was not created or used.

## Architecture

PASS. The five Core Engines retain their established responsibilities. Product modules
remain separated into Organizations, Users/Auth, Access, Bots, and Business
Configuration. The API delegates to application services, application services use
repositories, and ORM models stay in infrastructure. No circular dependency or product
logic embedded in a Core Engine was identified in the reviewed code paths.

## Security, RBAC, and Multi-Tenancy

PASS. Authentication uses Argon2 password hashes and JWTs containing `auth_version`.
Password changes and user deactivation invalidate prior tokens. Protected endpoints load
the current user and permissions from the database per request.

The Docker smoke validated the following HTTP outcomes:

| Case | Result |
| --- | --- |
| Viewer reads Business Configuration | `200` |
| Viewer updates Business Configuration | `403` |
| Operator creates Business Configuration | `403` |
| Cross-tenant Business Configuration read | `403` |
| Duplicate Business Configuration | `409` |
| Invalid Business Configuration payload | `422` |
| Platform admin cross-tenant read | `200` |
| Platform admin cross-tenant create | `201` |
| Deactivated user token | `403` |
| Last owner protection | Covered by passing RBAC regression tests |

User, Bot, and Business Configuration services use organization-scoped permission checks.
The database enforces globally unique user emails, per-organization bot slugs, and one
Business Configuration per bot.

## Docker, PostgreSQL, and Alembic

PASS. Docker daemon version was `29.6.1` for both client and server. `docker compose down
-v` followed by `docker compose up -d --build` created a clean PostgreSQL 17 instance;
PostgreSQL became healthy and API exposed `/health` and `/version` with `200`.

Alembic upgraded a clean database from initial revision through `20260728_0006`,
downgraded successfully to `20260728_0005`, and upgraded again successfully to the sole
head:

```
20260728_0006 (head)
```

Direct PostgreSQL inspection confirmed foreign keys, primary keys, and unique constraints
for `organization`, `app_user`, `bot`, and `business_configuration`.

## Persistence and Sessions

PASS. The Docker smoke created two organizations, five users, two bots, and two Business
Configuration records. Direct SQL confirmed persisted data, including the updated name
`RC Alpha Updated`. After `docker compose restart api`, `/health` returned `200` and the
two configuration rows remained present.

Thirty consecutive authenticated `/auth/me` requests all returned `200`. PostgreSQL then
reported one active audit query and one idle pooled connection. The session generator
closes sessions in `finally`; no pool exhaustion or unclosed-session symptom was observed.

## Quality Gates

PASS.

| Gate | Result |
| --- | --- |
| `pytest` | `545 passed, 1 warning in 110.69s` |
| `ruff check app tests` | `All checks passed!` |
| `black --check app tests` | `224 files would be left unchanged.` |
| `mypy app tests` | `Success: no issues found in 224 source files` |

The initial local test attempt exposed a stale `.venv` missing `argon2-cffi`. The package
was already correctly declared in `pyproject.toml`; synchronizing the environment with
`pip install -e ".[dev]"` restored the local gate. This was an environment issue, not a
repository defect.

## Documentation Review

Corrected a real README inconsistency: its detailed test section still said `491 tests
passing` while the official current result is `545 passed, 1 warning`. Project status,
roadmap, CONTEXT_FOR_AI, engineering status, and PRD-005 documents consistently report
PRD-005 closed and PRD-006 not started. Historical PRD-004 documentation mentioning
PRD-005 as not started remains historical evidence and was not rewritten.

## Remaining Debt and Dependencies

### Non-blocking debt

- Business Configuration is persisted and administered, but is not yet consumed by the
  Core decision flow.
- Bot-to-channel routing and knowledge scoping by bot remain future product work.
- CI/CD is not present in the reviewed repository.

### External dependency

- WhatsApp real/live remains `BLOCKED - EXTERNAL CREDENTIALS REQUIRED`. Local webhook,
  mapper, sender, controlled error behavior, and contract tests are present; no live Meta
  credentials were available for this review.

### Blocking debt

None found.

## Defects Found and Corrected

One documentation defect was corrected: the stale README test count. No code, test,
migration, security, RBAC, multi-tenant, persistence, or API defect was found that
required correction.

## Release Recommendation

`RELEASE CANDIDATE APPROVED WITH NON-BLOCKING DEBT`

The release is suitable for CTO review. No tag should be created until CTO approval.
