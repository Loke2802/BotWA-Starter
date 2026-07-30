# PRD-006 Knowledge Management

**Status:** IN PROGRESS - implementation complete, pending CTO review and merge  
**Date:** 2026-07-29  
**Product milestone:** MVP, increment 6 of 10

## Problem

BotWA needs a product-facing way to manage the knowledge available to each bot
without mixing tenants or replacing the existing Knowledge Engine. The current
Core catalog is not an administrative product surface and the conversation
runtime does not yet resolve the organization and bot associated with a channel.

## Objectives

- Manage manual knowledge entries scoped to one organization and one bot.
- Provide deterministic publication and archival states.
- Enforce the existing RBAC and tenant boundaries.
- Offer SQL-backed filtering, text search, and pagination.
- Expose an isolated provider that returns only published entries for an explicit
  organization and bot.

## Scope

- Domain contracts for knowledge entries.
- Application service and repository contract.
- SQLAlchemy and in-memory repositories.
- PostgreSQL model and Alembic migration.
- Administrative API, FastAPI dependencies, and RBAC integration.
- Isolated bot-scoped provider.
- Automated tests and Docker/PostgreSQL validation.

## Out Of Scope

- PRD-007 WhatsApp Configuration or bot-to-channel routing.
- Changes to `ConversationMessage` or the public conversation contract.
- Connection to `get_conversation_service()`.
- PDF upload, web scraping, bulk import, complex versioning, or frontend.
- Embeddings, vector databases, semantic search, external RAG, or cloud providers.
- Changes to the responsibilities of the five Core Engines.

## Actors And Permissions

| Role | Permissions |
|---|---|
| `viewer` | `knowledge.read` |
| `operator` | `knowledge.read`, `knowledge.create`, `knowledge.update` |
| `organization_owner` | Full knowledge control |
| `organization_admin` | Full knowledge control |
| `platform_admin` | Full control with the existing cross-tenant mechanism |

Full control comprises `knowledge.read`, `knowledge.create`, `knowledge.update`,
`knowledge.delete`, and `knowledge.publish`. Archival requires
`knowledge.delete`.

## Data Model

`KnowledgeEntry` contains:

- `id`: UUID primary key.
- `organization_id`: required FK to `organization`.
- `bot_id`: required FK to `bot`.
- `title`: required trimmed string, maximum 200 characters.
- `content`: required trimmed text, maximum 20,000 characters.
- `status`: `draft`, `published`, or `archived`.
- `source_type`: `manual`.
- `metadata`: optional JSON object, represented as an empty object by default.
- `created_by_user_id`: required FK to `app_user`.
- `updated_by_user_id`: optional FK to `app_user`.
- `created_at` and `updated_at`: timezone-aware timestamps.

Indexes exist for `organization_id`, `bot_id`, `status`, and the composite
`organization_id, bot_id, status`.

## Contracts

- `KnowledgeEntryCreate`: accepts `title`, `content`, and optional `metadata`;
  the created status is always `draft`.
- `KnowledgeEntryUpdate`: accepts partial `title`, `content`, and `metadata`;
  scope and status cannot be changed through this contract.
- `KnowledgeEntryResponse`: wraps one `KnowledgeEntry`.
- `KnowledgeEntryListResponse`: returns `items`, `total`, `page`, and
  `page_size`.
- Unknown request fields are rejected.

## Endpoints

Base path:
`/organizations/{organization_id}/bots/{bot_id}/knowledge`

| Method | Path suffix | Result |
|---|---|---|
| `POST` | `/` | Create a draft, `201` |
| `GET` | `/` | Tenant-scoped list, `200` |
| `GET` | `/{knowledge_id}` | Read one entry, `200` |
| `PATCH` | `/{knowledge_id}` | Update content or metadata, `200` |
| `DELETE` | `/{knowledge_id}` | Physical deletion, `204` |
| `POST` | `/{knowledge_id}/publish` | Publish a draft, `200` |
| `POST` | `/{knowledge_id}/archive` | Archive a draft or published entry, `200` |

The list supports `status`, basic `search` over title/content, `page`, and
`page_size`. Pagination is executed in SQL with a maximum page size of 100.

## Business Rules

1. Every entry belongs to exactly one organization and one bot.
2. The bot must exist and belong to the organization in the path.
3. Every administrative repository query filters by both organization and bot.
4. Organization-scoped users cannot access another tenant; platform admins use
   the existing scoped authorization mechanism.
5. Writes require an active organization.
6. Only `published` entries are returned by the isolated provider.
7. Valid transitions are `draft -> published`, `draft -> archived`, and
   `published -> archived`.
8. `published -> draft` and restoration from `archived` are intentionally not
   supported in PRD-006.
9. Archived entries cannot be edited.
10. Known persistence conflicts roll back the transaction and return HTTP `409`
    without exposing PostgreSQL details.

## Security And Multi-Tenancy

- Authentication and permission checks use the existing PRD-002/PRD-003
  dependencies and RBAC matrix.
- Scope authorization runs before bot lookup for tenant users.
- Bot ownership is validated on every use case.
- Entry reads and writes use `organization_id`, `bot_id`, and entry ID together.
- Cross-tenant requests return `403`; resources outside an authorized scoped
  bot are returned as `404`.
- API dependencies create and close one SQLAlchemy session per request.

## Provider And Core Boundary

`BotKnowledgeProvider.retrieve_published()` requires explicit
`organization_id` and `bot_id`, supports basic search and a bounded limit, and
returns only `published` entries in that exact scope. It is isolated from the
administrative API and preserves in-memory repository support for tests.

### BLOCKED RUNTIME INTEGRATION

The conversation runtime currently does not resolve organization_id and bot_id.
The bot-scoped Knowledge provider is implemented and tested, but its runtime
connection to the Conversation Core is deferred to PRD-007 WhatsApp
Configuration, where bot-to-channel routing will establish that identity.

## Migration Strategy

Migration `20260729_0007` follows `20260728_0006`, creates
`knowledge_entry`, its foreign keys, status/source constraints, and tenant/query
indexes. Validation must cover:

```text
alembic upgrade head
alembic downgrade 20260728_0006
alembic upgrade head
alembic heads
```

There must be one head: `20260729_0007`.

## Test Strategy

- Domain validation and immutable DTO contracts.
- Service rules, state transitions, inactive organizations, and rollback on
  `IntegrityError`.
- In-memory and SQLAlchemy repository behavior.
- SQL pagination and title/content filters.
- RBAC for viewer, operator, owner/admin, platform admin, and inactive users.
- Tenant isolation and rejection of a bot from another organization.
- Provider inclusion of published entries and exclusion of draft, archived,
  other-bot, and other-organization entries.
- Migration metadata and Docker/PostgreSQL upgrade/downgrade.
- Persistence across API restart.
- Full regression gates for existing PRD and Core behavior.

## Acceptance Criteria

- All endpoints implement the documented status codes.
- All SQL queries are scoped by organization and bot.
- Pagination executes in the repository rather than in application memory.
- Invalid transitions return `409`.
- RBAC and cross-tenant tests pass.
- The provider returns only published entries for explicit scope.
- Alembic has one head at `20260729_0007`.
- Pytest, Ruff, Black, and mypy pass.
- Docker/PostgreSQL smoke and restart persistence pass.
- No Core Engine or conversation contract is changed.

## Validation Results

- Pytest: 557 passed, 1 warning.
- Ruff: all checks passed.
- Black: 239 files would be left unchanged.
- mypy: no issues found in 239 source files.
- Docker Compose: API and PostgreSQL started from a clean volume.
- Alembic: upgrade/downgrade/upgrade passed with one head at `20260729_0007`.
- HTTP smoke: health/version, draft creation, reading, filtering, publication,
  invalid-transition conflict, archival, and restart read passed.
- RBAC: viewer modification, operator publication, and normal-user cross-tenant
  access were denied; platform-admin cross-tenant read passed.
- Provider: published entry returned for exact scope; draft, archived, and wrong
  tenant scope returned no entries.
- PostgreSQL: foreign keys, checks, indexes, JSON metadata, and restart
  persistence verified.

## Future Debt

- Connect the provider to the conversation runtime only after PRD-007 establishes
  bot-to-channel identity.
- Evaluate richer ingestion and retrieval only under a future approved PRD.
- CI/CD remains separate from this product increment.
