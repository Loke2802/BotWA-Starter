# BotWA Starter - Context For AI Assistants

**Last updated:** 2026-07-28  
**Project phase:** Core v1.0.0 - Phase 2 Closed  
**Purpose:** Align AI assistants with the current official state of BotWA before suggesting or making changes.

## Official Current State

BotWA is a multi-engine conversational assistant platform with WhatsApp Cloud API integration, persistence, automation, integration providers, and deterministic quality gates. Core v1.0.0 is validated and Phase 2 is closed.

All five core engines are implemented and closed:

| Engine | Status | Scope |
|---|---|---|
| ENG-001 Business Brain | CLOSED | Business context, intent, rules, decisions, confidence, action planning, events |
| ENG-002 Conversation Engine | CLOSED | Message routing, context, state, topics, response composition, channel adaptation |
| ENG-003 Knowledge Engine | CLOSED | Retrieval, normalization, resolution, validation, publishing, DB catalog |
| ENG-004 Automation Engine | CLOSED | Request building, workflow planning, task registry/orchestration, monitoring, persistence |
| ENG-005 Integration Engine | CLOSED | Gateway, provider resolution, clients, credentials/configuration, rate limiting, circuit breaker, monitoring, health checks |

## Quality Gates

Current stabilized gates:

| Gate | Result |
|---|---|
| `pytest` | 470 passed |
| `ruff check app tests` | clean |
| `black --check app tests` | clean |
| `mypy app tests` | clean |

## Infrastructure Validation

| Area | Result |
|---|---|
| Docker/PostgreSQL | PASS |
| Alembic migrations | PASS - `20260728_0001` |
| DB-backed persistence | PASS |
| Docker smoke tests | PASS |
| Integration controlled errors | PASS |
| WhatsApp local contracts/webhook/sender | PASS |
| WhatsApp real/live | BLOCKED - EXTERNAL CREDENTIALS REQUIRED |

## Runtime And Testing Notes

- Local tests run without Docker/PostgreSQL in in-memory mode.
- Tests explicitly force `BOTWA_USE_DATABASE=false`.
- Docker/PostgreSQL validation has passed for Core v1.0.0.
- Do not rely on `.env` local database settings when running unit/local quality gates.

## Binding Constraints For AI Assistants

- Do not modify Blueprints.
- Do not modify ADRs.
- Do not create new engines.
- Do not move responsibilities between engines.
- Do not change public contracts unless explicitly approved by CTO.
- Do not add product functionality during stabilization/status work.
- Do not re-open closed engines without explicit CTO direction.

## Current Official Objective

The next step is Product Development preparation, not new engine development.

**Phase 3**

1. CTO review of Phase 2 closure.
2. Use `PHASE_3_KICKOFF.md` as the kickoff document.
3. Implement `PRD-001_ORGANIZATIONS.md` only after explicit approval.

## Remaining Real Debt

The stabilization-specific debts below are resolved and should not be treated as active backlog:

- Test/runtime configuration.
- SQLAlchemy typing for `IntegrationEventModel`.
- Async lifecycle handling.
- Immutable contract test typing.
- Integration generic typing.
- Lint hygiene.
- README drift.

Active post-closure debt:

- Validate WhatsApp with real credentials and webhook.
- Add CI/CD after the local Core release is tagged.

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
