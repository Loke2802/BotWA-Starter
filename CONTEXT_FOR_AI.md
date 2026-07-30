# BotWA Starter - Context For AI Assistants

**Last updated:** 2026-07-29  
**Project phase:** Phase 3 - PRD-006 Knowledge Management In Progress
**Purpose:** Align AI assistants with the current official state of BotWA before suggesting or making changes.

## Official Current State

BotWA is a multi-engine conversational assistant platform with WhatsApp Cloud API
integration, persistence, automation, integration providers, and deterministic
quality gates. Core v1.0.0 is validated and Phase 2 is closed.

Product v1.0.0 is released. PRD-001 Organizations, PRD-002 Authentication and
Users, PRD-003 Roles and Permissions, PRD-004 Bot Management, and PRD-005
Business Configuration are implemented and closed. PRD-006 Knowledge
Management is implemented on its feature branch and awaits CTO review.

All five core engines are implemented and closed:

| Engine | Status | Scope |
|---|---|---|
| ENG-001 Business Brain | CLOSED | Business context, intent, rules, decisions, confidence, action planning, events |
| ENG-002 Conversation Engine | CLOSED | Message routing, context, state, topics, response composition, channel adaptation |
| ENG-003 Knowledge Engine | CLOSED | Retrieval, normalization, resolution, validation, publishing, DB catalog |
| ENG-004 Automation Engine | CLOSED | Request building, workflow planning, task registry/orchestration, monitoring, persistence |
| ENG-005 Integration Engine | CLOSED | Gateway, provider resolution, clients, credentials/configuration, rate limiting, circuit breaker, monitoring, health checks |

## Quality Gates

Current validated gates:

| Gate | Result |
|---|---|
| `pytest` | 557 passed, 1 warning |
| `ruff check app tests` | All checks passed |
| `black --check app tests` | 239 files would be left unchanged |
| `mypy app tests` | Success: no issues found in 239 source files |

## Infrastructure Validation

| Area | Result |
|---|---|
| Docker/PostgreSQL | PASS |
| Alembic migrations | PASS - `20260729_0007 (head)`, one head |
| DB-backed product persistence | PASS - KnowledgeEntry survives API restart |
| Docker smoke tests | PASS - PRD-006 lifecycle, RBAC, tenancy, filters, provider |
| Integration controlled errors | PASS |
| WhatsApp local contracts/webhook/sender | PASS |
| WhatsApp real/live | BLOCKED - EXTERNAL CREDENTIALS REQUIRED |

## Runtime And Testing Notes

- Local tests run without Docker/PostgreSQL in in-memory mode.
- Tests explicitly force `BOTWA_USE_DATABASE=false`.
- Docker/PostgreSQL validation has passed for Core and product persistence increments.
- Do not rely on `.env` local database settings when running unit/local quality gates.
- DB-backed FastAPI service dependencies must close SQLAlchemy sessions per request.

## Binding Constraints For AI Assistants

- Do not modify Blueprints.
- Do not modify ADRs.
- Do not create new engines.
- Do not move responsibilities between engines.
- Do not change public contracts unless explicitly approved by CTO.
- Do not add product functionality without a PRD.
- Do not re-open closed engines without explicit CTO direction.

## Current Official Objective

The next step is complete validation and CTO review of PRD-006. Do not start
PRD-007 without explicit CTO approval.

**Phase 3**

| Order | Increment | Status |
|---|---|---|
| 1 | PRD-001 Organizations | CLOSED |
| 2 | PRD-002 Authentication and Users | CLOSED |
| 3 | PRD-003 Roles and Permissions | CLOSED |
| 4 | PRD-004 Bot Management | CLOSED |
| 5 | PRD-005 Business Configuration | CLOSED |
| 6 | PRD-006 Knowledge Management | IN PROGRESS |
| 7 | PRD-007 WhatsApp Configuration | NOT STARTED |
| 8 | PRD-008 WhatsApp Live Messaging | NOT STARTED |
| 9 | PRD-009 Conversations Management | NOT STARTED |
| 10 | PRD-010 Human Handoff | NOT STARTED |
| 11-22 | Future approved product increments | NOT STARTED |

The MVP milestone comprises PRD-001 through PRD-010.

## PRD-006 Knowledge Management

- Administrative knowledge entries are scoped by `organization_id` and `bot_id`.
- States are `draft`, `published`, and `archived`.
- RBAC uses `knowledge.read`, `knowledge.create`, `knowledge.update`,
  `knowledge.delete`, and `knowledge.publish`.
- Lists use SQL filtering and pagination with `items`, `total`, `page`, and
  `page_size`.
- `BotKnowledgeProvider` requires explicit organization and bot identifiers and
  returns only published entries.
- Migration target is `20260729_0007`.

### BLOCKED RUNTIME INTEGRATION

The conversation runtime currently does not resolve organization_id and bot_id.
The bot-scoped Knowledge provider is implemented and tested, but its runtime
connection to the Conversation Core is deferred to PRD-007 WhatsApp
Configuration, where bot-to-channel routing will establish that identity.

## Remaining Real Debt

The stabilization-specific debts below are resolved and should not be treated as active backlog:

- Test/runtime configuration.
- SQLAlchemy typing for `IntegrationEventModel`.
- Async lifecycle handling.
- Immutable contract test typing.
- Integration generic typing.
- Lint hygiene.
- README drift.
- DB session lifecycle under Docker smoke traffic.

Active post-closure debt:

- Validate WhatsApp with real credentials and webhook.
- Add CI/CD after the local Core release is tagged.
- Connect bot-scoped Knowledge to Conversation only after PRD-007 provides
  bot-to-channel identity.

## Technology Baseline

- Python 3.13+
- FastAPI
- SQLAlchemy 2.0
- Alembic
- PostgreSQL via Docker for DB validation
- pytest
- ruff
- black
- mypy strict

## CTO Review Status

READY FOR CTO REVIEW
