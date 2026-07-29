# BotWA Starter - Context For AI Assistants

**Last updated:** 2026-07-29  
**Project phase:** Phase 3 - PRD-005 Business Configuration Closed  
**Purpose:** Align AI assistants with the current official state of BotWA before suggesting or making changes.

## Official Current State

BotWA is a multi-engine conversational assistant platform with WhatsApp Cloud API
integration, persistence, automation, integration providers, and deterministic
quality gates. Core v1.0.0 is validated and Phase 2 is closed.

PRD-001 Organizations, PRD-002 Authentication and Users, PRD-003 Roles and
Permissions, PRD-004 Bot Management, and PRD-005 Business Configuration are
implemented and closed as Phase 3 product increments.

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
| `pytest` | 545 passed, 1 warning |
| `ruff check app tests` | All checks passed |
| `black --check app tests` | 224 files would be left unchanged |
| `mypy app tests` | Success: no issues found in 224 source files |

## Infrastructure Validation

| Area | Result |
|---|---|
| Docker/PostgreSQL | PASS |
| Alembic migrations | PASS - `20260728_0006 (head)` |
| DB-backed bot and business configuration persistence | PASS |
| Docker smoke tests | PASS |
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

The next step is CTO review of PRD-005. Do not start PRD-006 without explicit CTO approval.

**Phase 3**

| Order | Increment | Status |
|---|---|---|
| 1 | PRD-001 Organizations | CLOSED |
| 2 | PRD-002 Authentication and Users | CLOSED |
| 3 | PRD-003 Roles and Permissions | CLOSED |
| 4 | PRD-004 Bot Management | CLOSED |
| 5 | PRD-005 Business Configuration | CLOSED |
| 6 | PRD-006 | NOT STARTED |

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
- Define future PRDs for bot-to-channel routing and Core consumption of Business Configuration if required.

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
