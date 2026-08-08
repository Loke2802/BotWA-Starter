# BotWA Starter - Context For AI Assistants

**Last updated:** 2026-08-08
**Project phase:** Phase 3 - PRD-013 Integration Management and PRD-015 Business Hours & Holidays CLOSED
**Purpose:** Align AI assistants with the current official state of BotWA before suggesting or making changes.

## Official Current State

BotWA is a multi-engine conversational assistant platform with WhatsApp Cloud API
integration, persistence, automation, integration providers, and deterministic
quality gates. Core v1.0.0 is validated and Phase 2 is closed.

Product v1.0.0 is released. PRD-001 Organizations, PRD-002 Authentication and
Users, PRD-003 Roles and Permissions, PRD-004 Bot Management, and PRD-005
Business Configuration, PRD-006 Knowledge Management, and PRD-007 WhatsApp
Configuration and PRD-008 WhatsApp Live Messaging are implemented and closed.
PRD-009, PRD-010, PRD-011, and PRD-012 are closed. PRD-011 implements the
Contact increment only; Customer is deferred and CRM is not implemented.
PRD-012 adds tenant-scoped Automation Management without changing Core Automation.
PRD-013 Integration Management is CLOSED after the final security merge via PR
#20. PRD-015 Business Hours & Holidays is CLOSED after merge via PR #18. PRD-014
Dashboard and PRD-016 through PRD-023 remain NOT STARTED.

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
| `pytest` | 705 passed, 12 skipped, 2 warnings |
| Focused PRD-013 | 39 passed |
| PostgreSQL PRD-013 | 1 passed |
| PRD-012/015 compatibility | 18 passed |
| `ruff check app tests` | All checks passed |
| `black --check app tests` | 374 files would be left unchanged |
| `mypy app tests` | Success: no issues found in 374 source files |
| `git diff --check` | PASS |

## Infrastructure Validation

| Area | Result |
|---|---|
| Docker/PostgreSQL | PASS |
| Alembic migrations | PASS - `20260808_0016 (head)`, one head, PRD-015 cycle/smoke validated |
| DB-backed product persistence | PASS - receipts, managed encrypted messages, and delivery attempts survive API restart |
| Docker smoke tests | PASS - signed inbound, Core/Knowledge, fake outbound, lifecycle/RBAC, statuses, restart |
| Integration controlled errors | PASS |
| WhatsApp live-compatible contracts/webhook/sender | PASS |
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

PRD-001 through PRD-013 and PRD-015 are closed; PRD-014 Dashboard remains NOT
STARTED. PRD-016 through PRD-023 remain NOT STARTED.

**Phase 3**

| Order | Increment | Status |
|---|---|---|
| 1 | PRD-001 Organizations | CLOSED |
| 2 | PRD-002 Authentication and Users | CLOSED |
| 3 | PRD-003 Roles and Permissions | CLOSED |
| 4 | PRD-004 Bot Management | CLOSED |
| 5 | PRD-005 Business Configuration | CLOSED |
| 6 | PRD-006 Knowledge Management | CLOSED |
| 7 | PRD-007 WhatsApp Configuration | CLOSED |
| 8 | PRD-008 WhatsApp Live Messaging | CLOSED |
| 9 | PRD-009 Conversations Management | CLOSED |
| 10 | PRD-010 Human Handoff | CLOSED |
| 11 | PRD-011 Contacts and Customers | CLOSED (Contact only; Customer deferred; CRM not implemented) |
| 12 | PRD-012 Automation Management | CLOSED |
| 13 | PRD-013 Integration Management | CLOSED |
| 14 | PRD-014 Dashboard | NOT STARTED |
| 15 | PRD-015 Business Hours & Holidays | CLOSED |
| 16-23 | Future approved product increments | NOT STARTED |

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
- PRD-006 migration revision is `20260729_0007`; the current project head is
  `20260808_0016`.

### Runtime Integration Status

PRD-007 provides generic `ResolvedChannelContext` identity and a
`WhatsAppChannelResolver`. PRD-008 consumes the resolved identity through a
generic channel handler, bot-scoped Knowledge lookup, the unchanged
`ConversationService`, and a scoped outbound sender.

## PRD-007 WhatsApp Configuration

- BotWA remains multichannel; WhatsApp is the first production adapter.
- Generic channel contracts do not depend on Meta or WhatsApp DTOs.
- WhatsApp configurations are tenant/bot scoped and have draft/active/inactive
  lifecycle.
- Secrets use environment-backed authenticated encryption and safe output flags.
- Runtime lookup uses globally unique indexed phone number IDs.
- Webhook verification and HMAC validation are configuration-specific.
- Uvicorn access logs redact `hub.verify_token`.
- Live message processing is owned by PRD-008; PRD-007 remains the
  configuration and identity boundary.

## PRD-008 WhatsApp Live Messaging

- Signed POST webhooks validate HMAC over raw bytes before JSON parsing.
- Text messages use generic channel contracts; unsupported media is acknowledged
  without entering the Core.
- Durable receipts protect Core execution from sequential and concurrent
  webhook duplicates.
- Outbound attempts persist encrypted recipient/text, bounded retry state, and
  monotonic provider delivery statuses.
- Client mode defaults to `disabled`; `fake` and `meta` require explicit
  configuration.
- No Core Engine or public conversation contract was changed.

## PRD-009 Conversations Management

- Extends existing `conversation` and `message` persistence; it does not create
  a second conversation-history source.
- Administrative lifecycle is separate from Core state: `open`, `closed`, and
  `archived` belong to PRD-009; agent states remain PRD-010 scope.
- Managed history is organization/bot/channel/customer scoped, paginated in SQL,
  and protects content with existing authenticated encryption.
- `InboundMessageReceipt` and `OutboundMessageAttempt` remain transport records;
  administrative messages link to them optionally and never drive retry.
- `conversation.read_content` is distinct from metadata-only `conversation.read`.
- Current target Alembic head is `20260730_0010`.

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

- Validate WhatsApp with approved real Meta credentials and webhook.
- Add CI/CD after the local Core release is tagged.
- Add a scheduled worker for due outbound retries.
- Define recovery for receipts left in `processing` after a process crash.
- Define retention and safe preview/full-text search policy for managed history.

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

## PRD-010 through PRD-015 Status

PRD-001 through PRD-012 are closed. PRD-010 preserves its boundaries: human
replies use the generic sender, remain encrypted and idempotent, and active
handoffs suppress automation. PRD-011 delivers Contact only; Customer is deferred
and CRM is not implemented. PRD-012 Automation Management is CLOSED; PRD-013 is
CLOSED after final security merge via PR #20, merge commit
`be52bbc49c6b34fc6b515e915564810068a74da3`, final review head
`beb3a6a01c5a983ab5d83a485f268dfc3202fa3b`. PRD-015 is CLOSED after merge via
PR #18, merge commit `025c3058388d51219e05fff1ae253a296238be89`.
PRD-014 Dashboard and PRD-016 through PRD-023 are NOT STARTED.
