# Engineering Status Report - Official Current Status

**Date:** 2026-08-13
**Role:** Lead Engineer  
**Project phase:** Phase 3 - PRD-001 through PRD-019 CLOSED; PRD-020 IMPLEMENTED — PENDING CTO REVIEW
**Status source:** PRD-020 implementation branch pending CTO review

## Executive Summary

BotWA Core v1.0.0 is validated and Phase 2 is formally closed. The five planned
core engines are implemented and closed:

| Engine | Status |
|---|---|
| ENG-001 Business Brain | CLOSED |
| ENG-002 Conversation Engine | CLOSED |
| ENG-003 Knowledge Engine | CLOSED |
| ENG-004 Automation Engine | CLOSED |
| ENG-005 Integration Engine | CLOSED |

The Stabilization Sprint recovered all quality gates, and Docker/PostgreSQL
validation confirmed real DB-backed runtime operation.

PRD-001 through PRD-012 are closed. PRD-011 implements Contact without changing
Core Engine responsibilities: encrypted tenant-scoped identity, inbound resolution,
administrative API, and explicit idempotent historical backfill. Customer is
deferred and CRM is not implemented. PRD-012 adds durable, tenant-scoped Automation
Management while remaining separate from Core Automation Engine.
PRD-013 is CLOSED after the final security merge via PR #20, with encrypted
credentials, secure Google OAuth, read-only Calendar capabilities and on-demand
health.
PRD-015 is CLOSED after merge via PR #18 with a provider-agnostic operational
calendar, deterministic precedence, IANA timezone/DST handling, tenant-scoped
administration, RBAC, durable audit/idempotency, and PostgreSQL persistence.
PRD-014 is CLOSED after merge via PR #22 as a tenant-scoped, query-only
operational read model over the existing product Sources of Truth. Its closure
freezes the read-only boundary: no Dashboard tables or migration, frontend,
activity endpoint or PRD-016 scope; no health checks, OAuth refresh, automation
execution, handoff claims or Business Hours writes; organization-scoped Contacts,
active-only Integration health breakdown, canonical PRD-015/PRD-005 resolution
and no PII in responses.
PRD-016 is CLOSED after merge via PR #24. It adds tenant-scoped historical
Conversation/Handoff sources, a rebuildable daily PostgreSQL projection,
bounded comparisons and aggregate CSV without replacing operational Sources of
Truth or advancing PRD-017.

PRD-017 is CLOSED after merge via PR #26. It adds a tenant-scoped,
append-only administrative ledger with success-only same-transaction writes,
typed allowlisted metadata, no PII/secrets, signed keyset pagination,
`audit.read`, strict tenant isolation and revision `20260808_0018`. Existing
domain histories remain separate and no pre-PRD-017 history is fabricated. The
final hardening makes `AuditWriter` mandatory and fail-closed across production
composition paths; `audit_append_attempts_total` reports only unit-of-work
acceptance/rejection, never durable persistence.

PRD-018 is CLOSED after PR #28 at merge commit
`63f2fc79444e6b3f85b516b917860fb17fa8f779`, with final approved head
`2776a1b2ca6082142f14862c4eac4cf889eea631`. It adds an internal tenant-scoped
plan catalog and current 1:1 Organization assignment, closed boolean entitlements,
operational resource-count hard limits, application-service enforcement,
Organization row locking, optimistic concurrency, safe APIs/RBAC and
same-transaction PRD-017 Audit. The default bootstrap is backward-compatible and
unlimited. Downgrades are non-destructive and do not stop existing runtimes.
Revision `20260810_0019` is PostgreSQL-only.

PRD-019 is CLOSED after normal merge PR #30 at
`5a87ffc32be4315ebb6f9e64826bdb96f36ada58`, with final approved implementation
head `2a15b7f022c2989d73bb97d9b964495dba961778`. It adds provider-agnostic,
Organization-scoped Billing, Mercado Pago/fake adapters, hosted checkout, a durable
provider-event ledger, authoritative webhook/reconcile transitions and
same-transaction Plan/Audit application. Revision `20260812_0020` is
PostgreSQL-only and contains no commercial seeds. Billing remains disabled by
default. Mercado Pago cancellation is immediate and provider-confirmed while Luri
preserves paid access until period end; scheduled downgrades require both their
effective time and authoritative target-price confirmation. A bounded one-shot
processor supplies the production temporal trigger through an external scheduler;
manual reconcile remains a recovery tool. Plan enforcement continues to read only
`organization_plan_assignment`; Billing is not queried on each enforced request.
Real Mercado Pago sandbox and commercial go-live gates remain pending operational
enablement requirements and do not block the technical closure.

PRD-020 is IMPLEMENTED — PENDING CTO REVIEW. Its hybrid model persists only
historical start/completion in `organization_onboarding` and derives current
readiness directly from Organization, Users, Plan, Bots, Business Configuration,
WhatsApp, Knowledge and Integration Sources of Truth. It adds revision
`20260813_0021`, tenant-scoped read/start/complete APIs, deterministic multi-Bot
selection, closed DTOs/errors, least-privilege RBAC, same-transaction fail-closed
Audit, optimistic versioning and Organization-first locking. It creates no runtime
gate, performs no external checks or resource mutation, and leaves PRD-021 onward
NOT STARTED.

## Quality Gates

| Gate | Current result |
|---|---|
| `pytest` | 843 passed, 29 skipped, 2 warnings |
| Focused PRD-020 | 22 passed |
| Affected-domain regression | 123 passed |
| PostgreSQL PRD-020 | 3 passed |
| PostgreSQL migration cycle | `0020 → 0021 → 0020 → 0021` PASS |
| `ruff check app tests` | All checks passed |
| `black --check app tests` | 463 files would be left unchanged |
| `mypy app tests` | Success: no issues found in 463 source files |
| `git diff --check` | PASS |
| Alembic | `20260813_0021 (head)` |

## Phase 3 Product Status

| Increment | Current result |
|---|---|
| PRD-001 Organizations | CLOSED |
| PRD-002 Authentication and Users | CLOSED |
| PRD-003 Roles and Permissions | CLOSED |
| PRD-004 Bot Management | CLOSED |
| PRD-005 Business Configuration | CLOSED |
| PRD-006 Knowledge Management | CLOSED |
| PRD-007 WhatsApp Configuration | CLOSED |
| PRD-008 WhatsApp Live Messaging | CLOSED |
| PRD-009 Conversations Management | CLOSED |
| PRD-010 Human Handoff | CLOSED |
| PRD-011 Contacts and Customers | CLOSED (Contact only; Customer deferred; CRM not implemented) |
| PRD-012 Automation Management | CLOSED |
| PRD-013 Integration Management | CLOSED |
| PRD-014 Dashboard | CLOSED |
| PRD-015 Business Hours & Holidays | CLOSED |
| PRD-016 Analytics & Reports | CLOSED |
| PRD-017 Audit Log | CLOSED |
| PRD-018 Plans and Limits | CLOSED |
| PRD-019 Billing & Subscriptions | CLOSED |
| PRD-020 Onboarding | IMPLEMENTED — PENDING CTO REVIEW |
| PRD-021 through PRD-023 | NOT STARTED |

## PRD-004 Bot Management

| Area | Current result |
|---|---|
| Bot domain contracts | PASS |
| Bot application service | PASS |
| Bot API endpoints | PASS |
| PostgreSQL persistence | PASS |
| Alembic migration | PASS - `20260728_0005` |
| RBAC permissions | PASS |
| Multi-tenancy | PASS |
| Slug unique per tenant | PASS |
| Activation/deactivation idempotency | PASS |
| Inactive organization write blocking | PASS |
| Docker smoke tests | PASS |
| PRD-005 | Closed |

## PRD-005 Business Configuration

| Area | Current result |
|---|---|
| Business Configuration domain contracts | PASS |
| Application service | PASS |
| API endpoints | PASS |
| PostgreSQL persistence | PASS |
| Alembic migration | PASS - `20260728_0006` |
| RBAC permissions | PASS |
| Multi-tenancy | PASS |
| Structured validation | PASS |
| Inactive organization write blocking | PASS |
| Inactive bot read preservation | PASS |
| Docker smoke tests | PASS |
| PRD-006 | Closed |

## PRD-006 Knowledge Management

| Area | Current result |
|---|---|
| Domain contracts | PASS |
| Application service | PASS |
| Administrative API | PASS |
| RBAC integration | PASS |
| SQL tenant filtering and pagination | PASS |
| `IntegrityError` rollback and conflict translation | PASS |
| Isolated published-entry provider | PASS |
| Alembic migration | PASS - `20260729_0007`, one head |
| Automated regression suite | PASS - 572 passed, 1 warning |
| Docker/PostgreSQL validation | PASS - clean volume and API restart |
| Channel identity routing | PASS - consumed by the subsequent PRD-008 increment |
| PRD-007 | Validated locally; CTO review pending |

The provider requires explicit `organization_id` and `bot_id` and returns only
published entries. Draft and archived entries are excluded.

**IDENTITY ROUTING AND LIVE-COMPATIBLE TRANSPORT IMPLEMENTED**

PRD-007 resolves phone number identity into organization and bot context and
tests that context against `BotKnowledgeProvider`. PRD-008 now consumes that
context while preserving the generic channel and Core boundaries.

## PRD-007 WhatsApp Configuration

| Area | Current result |
|---|---|
| Generic channel contracts | PASS |
| WhatsApp configuration contracts/service/API | PASS |
| Environment-backed secret encryption | PASS |
| Secret rotation and safe flags | PASS |
| SQL tenant filtering and pagination | PASS |
| Global phone/webhook uniqueness | PASS |
| Row locking and `IntegrityError` rollback | PASS |
| WhatsApp channel resolver | PASS |
| Webhook verification and HMAC | PASS |
| Resolver-to-Knowledge integration | PASS |
| Alembic migration | PASS - `20260730_0008`, one head |
| Automated regression suite | PASS - 572 passed, 1 warning |
| Docker/PostgreSQL validation | PASS - migration cycle, smoke, restart persistence |
| Secret storage/logging | PASS - ciphertext at rest, safe DTOs, verify token redacted |
| PRD-008 | Implemented and validated on feature branch |

## PRD-008 WhatsApp Live Messaging

| Area | Current result |
|---|---|
| Generic inbound/outbound contracts | PASS |
| Signed configured webhook | PASS - HMAC before parsing, bounded body/events |
| Tenant/bot routing | PASS - PRD-007 resolver reused |
| Conversation Core and Knowledge | PASS - unchanged Core, published bot scope |
| Inbound idempotency | PASS - sequential and concurrent duplicates |
| Outbound sender/client | PASS - explicit disabled/fake/meta modes |
| Retry classification and persistence | PASS - bounded persisted backoff |
| Delivery status events | PASS - idempotent, monotonic ordering |
| Secret and content handling | PASS - encrypted at rest, metadata-only logs |
| Alembic migration | PASS - `20260730_0009`, one head |
| Automated regression suite | PASS - 603 passed, 1 warning |
| Docker/PostgreSQL validation | PASS - clean volume, migration cycle, restart |
| Real Meta validation | BLOCKED - EXTERNAL CREDENTIALS REQUIRED |
| PRD-009 | CLOSED |

## PRD-009 Conversations Management

| Area | Current result |
|---|---|
| Existing conversation/message source | Extended, not duplicated |
| Tenant/bot/channel identity | PASS - partial unique managed identity |
| Encrypted message records | PASS - managed plaintext column remains empty |
| Lifecycle | PASS - open, closed, archived, controlled reopen |
| Transport links | PASS - receipt and outbound attempt references remain separate |
| API/RBAC | PASS - metadata and content permissions are separate |
| Pagination and isolation | PASS - SQL-scoped list/detail/message history |
| Alembic migration | PASS - `20260730_0010`, one head |
| Docker/PostgreSQL | PASS - clean volume, signed flow, restart, and migration cycle |
| PRD-010 | CLOSED |

## Infrastructure Validation

| Area | Current result |
|---|---|
| Docker daemon | PASS - Docker Desktop 4.82.0, engine 29.6.1 |
| Docker Compose | PASS - PostgreSQL and API started |
| PostgreSQL | PASS - database `botwa`, user `botwa` |
| Alembic | PASS - revision `20260805_0013 (head)`, post-merge smoke validated |
| DB persistence | PASS - receipts, conversations, messages, and encrypted outbound attempts survive API restart |
| Docker smoke tests | PASS - health, version, signed inbound, Core/Knowledge, fake outbound, deduplication, statuses |
| Integration controlled errors | PASS - covered by regression suite |

## Runtime And Test Mode

- Local tests run in in-memory mode without Docker/PostgreSQL.
- Docker/PostgreSQL validation has passed for Core and Phase 3 persistence increments.
- Runtime configuration keeps database-backed operation available for Docker/PostgreSQL.
- DB-backed FastAPI service dependencies close SQLAlchemy sessions per request.

## Stabilization Items Resolved

The following debts were resolved and should not be reopened as active backlog:

- Test/runtime configuration for `BOTWA_USE_DATABASE`.
- SQLAlchemy typing for `IntegrationEventModel`.
- Async lifecycle handling for Integration HealthChecker shutdown.
- Immutable contract test typing.
- Integration Engine generic typing.
- Ruff and black hygiene.
- README status drift.
- DB session lifecycle under Docker smoke traffic.

## Remaining Real Debt

Only the following items remain pending:

- Validate real WhatsApp Cloud API webhook and outbound flow with approved credentials or sandbox.
- Add CI/CD when the release branch is ready.
- Add a scheduled worker for due outbound retries.
- Define recovery for receipts left in `processing` after a process crash.

## Next Official Objective

**PRD-001 through PRD-019 are CLOSED. PRD-020 is IMPLEMENTED — PENDING CTO
REVIEW. PRD-021 through PRD-023 remain NOT STARTED.**

## PRD-010 through PRD-015 Status

PRD-010 through PRD-012 are closed. PostgreSQL validated lifecycle/RBAC, tenancy,
archive protection, encrypted replies, idempotency, transport-error mapping,
and isolated Docker smoke while preserving the original volume. The FK fix
flushes `HandoffSession` before `HandoffEvent`. PRD-011 provides Contact only;
Customer is deferred and CRM is not implemented. PRD-012 is CLOSED. PRD-013 is
CLOSED after PR #20 at merge commit
`be52bbc49c6b34fc6b515e915564810068a74da3`, final review head
`beb3a6a01c5a983ab5d83a485f268dfc3202fa3b`. PRD-015 is CLOSED after PR #18 at
merge commit `025c3058388d51219e05fff1ae253a296238be89`. PRD-014 Dashboard is
CLOSED after PR #22 at merge commit
`04256eb0cb17e3d1fdb548edeae143578606d508`, final approved head
`8b836d7bb7b12fcf82ffb5bb8bbada4f3db758c6`; PRD-016 is CLOSED after PR #24 at
merge commit `601499071f39aad85dc4d9595fc04425f40a3962`, final approved head
`6cafee11a0f807e07a9277eae98e128ab68aa711`. PRD-017 is CLOSED after PR #26 at
merge commit `01c809c909360f4a31a6b26b1d4126a1c98e9c8b`, final approved head
`3f7808da24d0dc1e3b5d6f3d337ee4562f5398b6`; PRD-018 is CLOSED after PR #28 at
merge commit `63f2fc79444e6b3f85b516b917860fb17fa8f779`, final approved head
`2776a1b2ca6082142f14862c4eac4cf889eea631`. PRD-019 is CLOSED after normal merge
PR #30 at `5a87ffc32be4315ebb6f9e64826bdb96f36ada58`, final approved
implementation head `2a15b7f022c2989d73bb97d9b964495dba961778`; PRD-020 is
IMPLEMENTED — PENDING CTO REVIEW and PRD-021 through PRD-023 remain NOT STARTED.

## CTO Review Status

PRD-019 CLOSED - PR #30 MERGED

PRD-018 CLOSED - PR #28 MERGED

PRD-017 CLOSED - PR #26 MERGED

PRD-016 CLOSED - PR #24 MERGED

PRD-014 CLOSED - PR #22 MERGED

PRD-013 CLOSED - PR #20 MERGED

Google real smoke remains `SKIPPED` because approved external credentials are
not available. Before enabling Google Calendar in staging or production, OAuth
consent, callback, refresh, Calendar List and FreeBusy must pass the real smoke.
This is an operational external-enablement gate, not a blocker for PRD-013 closure.

PRD-015 CLOSED — PR #18 MERGED
