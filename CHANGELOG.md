# Changelog

## PRD-019 Billing & Subscriptions v1 - 2026-08-12

### IMPLEMENTED — PENDING CTO REVIEW

- Added provider-agnostic Billing contracts and typed errors, Mercado Pago and
  deterministic fake adapters, explicit timeouts and environment-only secrets.
- Added PostgreSQL-only `billing_account`, `billing_price`, `subscription` and
  `billing_provider_event` via Alembic `20260812_0020`, with no commercial seeds.
- Added hosted idempotent checkout, verified/deduplicated authoritative webhooks,
  manual Platform Admin reconcile, optimistic concurrency, guarded period-end
  downgrade and provider-confirmed immediate no-renewal with paid-period access,
  local last-known-good reads and fail-closed fallback policy.
- Added shared internal Plan assignment staging so provider-confirmed Subscription,
  PRD-018 assignment and PRD-017 Audit commit in one local transaction.
- Added least-privilege Billing RBAC, tenant-scoped APIs, allowlisted audit metadata,
  low-cardinality metrics and responses without external identifiers or PII.
- Added a bounded due-transition processor and one-shot external-job command so
  paid access expires and downgrades advance without user activity, webhook luck,
  or manual reconcile; each tenant has an independent locked transaction.
- Validation: focused PRD-019 34 passed; due-transition processor 10 passed;
  scheduling/cancellation regression 17 passed; PRD-017/018/019 regression 95
  passed; PostgreSQL PRD-019 5 passed; full pytest 821 passed, 26 skipped,
  2 warnings; mypy PASS across 449 source files; Alembic cycle
  `0019 → 0020 → 0019 → 0020` PASS.
- Billing remains disabled by default. No Plan/BillingPrice commercial data was
  seeded. Real Mercado Pago sandbox smoke and commercial go-live remain blocked
  pending approved credentials/configuration. PRD-020 remains NOT STARTED.

## PRD-018 Plans and Limits v1 - 2026-08-10

### CLOSED after PR #28

- Merged into `master` via PR #28 at
  `63f2fc79444e6b3f85b516b917860fb17fa8f779`, with final approved head
  `2776a1b2ca6082142f14862c4eac4cf889eea631`.

- Added PostgreSQL-only `plan_definition` and 1:1
  `organization_plan_assignment` as the current plan Source of Truth.
- Added deterministic `default` seed and existing-Organization backfill that
  preserve all pre-PRD-018 behavior with enabled features and unlimited limits.
- Added closed typed feature/limit configuration, direct operational resource
  counts, safe errors, `plan.read`/`plan.assign`, and tenant-scoped GET/PUT APIs.
- Added application-service enforcement across Bots, Users, Integrations,
  Automations, Business Calendar, Knowledge, WhatsApp, Human Handoff, Analytics
  and Audit-read while preserving existing runtimes and reducing actions.
- Added Organization `FOR UPDATE`, optimistic assignment versioning, non-destructive
  downgrade/over-limit semantics and real PostgreSQL concurrency coverage.
- Extended PRD-017 with typed `plan.assigned`/`plan.changed` Audit contracts;
  Audit writes remain mandatory, same-transaction and never plan-gated.
- Added Alembic `20260810_0019`, including backfill and composite Bot/User count
  indexes; migration cycle `0018 → 0019 → 0018 → 0019` passes.
- Final validation: focused PRD-018 plus fail-closed 36 passed, 2 warnings;
  affected-domain regression 159 passed, 2 warnings; PostgreSQL PRD-018 3
  passed; full pytest 787 passed, 21 skipped, 2 warnings; mypy PASS across 430
  source files; Ruff PASS; Black PASS across 430 files; `git diff --check` PASS;
  Alembic head `20260810_0019`; migration cycle
  `0018 → 0019 → 0018 → 0019` PASS.
- Final hardening made `PlanEnforcementService` mandatory and fail-closed across
  every gated service and production composition root, while preserving reducing
  actions, Audit writes, and existing runtime paths after downgrade.
- Billing, subscriptions, pricing, currencies, trials, invoices, message quota,
  metered usage and overage remain exclusively deferred to PRD-019.

## PRD-017 Audit Log v1 - 2026-08-09

### CLOSED after PR #26

- Merged into `master` via PR #26 at
  `01c809c909360f4a31a6b26b1d4126a1c98e9c8b`, with final approved head
  `3f7808da24d0dc1e3b5d6f3d337ee4562f5398b6`.

- Added tenant-scoped append-only `audit_event` with success-only semantics,
  typed actor/role/action/resource contracts and safe metadata without PII or
  secrets.
- Added same-transaction Audit integration across Organization, User/RBAC, Bot,
  Conversation, Handoff, Automation, Integration and Business Calendar while
  preserving domain histories and Business Calendar dual-write.
- Added read-only query API, HMAC-signed keyset cursor, bounded UTC range,
  `audit.read`, tenant isolation, safe errors and low-cardinality metrics.
- Added Alembic `20260808_0018`, PostgreSQL FKs/JSONB/indexes, rollback and
  migration cycle, plus a 10.000-event O(1) query fixture.
- History begins at PRD-017 without backfill. Denials, OAuth callback, Analytics
  export, automated retention, export/UI/SIEM and PRD-018 remain excluded.
- Hardened all classified administrative write services so `AuditWriter` is a
  required constructor dependency; helpers and the WhatsApp auto-reopen
  repository can no longer silently bypass Audit.
- Renamed append observability to `audit_append_attempts_total`: it reports unit
  of work acceptance/rejection and never claims flush, commit, or durability.
- Validation: focused 25 passed; expanded fail-closed/domain regression 82
  passed; PostgreSQL 3 passed; full pytest 751 passed, 18 skipped, 2 warnings;
  mypy/Ruff/Black/diff check PASS across 415 files;
  Alembic head `20260808_0018`; cycle `0017 → 0018 → 0017 → 0018` PASS.

## PRD-016 Analytics & Reports v1 - 2026-08-08

### CLOSED after PR #24

- Merged into `master` via PR #24 at
  `601499071f39aad85dc4d9595fc04425f40a3962`; final approved head:
  `6cafee11a0f807e07a9277eae98e128ab68aa711`.

- Added append-only Conversation Management transition history and non-reusable
  Human Handoff cycles, transactionally coupled to their operational changes.
- Added `analytics_daily_summary` with bot and organization grains, partial
  uniqueness, nonnegative BIGINT metrics, reporting timezone, source watermark,
  deterministic recalculation and concurrent PostgreSQL UPSERT.
- Added bounded day/week/month reads, completeness reporting, weighted Handoff
  averages, current Automation outcomes with retry correction, equal previous
  period comparison and aggregate CSV without PII.
- Added `analytics.read` and `analytics.export`, explicit tenant/bot isolation,
  safe errors, low-cardinality observability, and read-only GET/export behavior.
- Added Alembic revision `20260808_0017` and real PostgreSQL validation for
  partial indexes, concurrency, rollback, handoff persistence, isolation, CSV,
  and upgrade/downgrade/re-upgrade.
- Historical closure and handoff coverage starts with PRD-016; no prior history
  is fabricated. Automation failure is the current terminal outcome, not an
  attempt ledger. PRD-017 remains NOT STARTED.
- Final validation: pytest 726 passed, 15 skipped, 2 warnings; focused PRD-016
  plus Conversation/Handoff regression 34 passed; PostgreSQL PRD-016 2 passed;
  mypy PASS across 400 source files; Ruff PASS; Black PASS across 400 files;
  `git diff --check` PASS; migration cycle PASS; Alembic head `20260808_0017`.
- Final CTO completeness hardening makes expected bot coverage temporal using
  `Bot.created_at < bucket_end_utc`, skips fake pre-creation bot rows, preserves
  inactive-bot history, requires the organization Contacts row in bot responses,
  and defines `source_watermark_at` as a recomputable cutoff rather than a strong
  transactional snapshot.
- Closure freezes Analytics as a reporting-timezone-aware, rebuildable read model
  rather than a Source of Truth. Conversation and Handoff history start at
  PRD-016, Automation exposes the current terminal outcome rather than an attempt
  ledger, Contacts remains organization-scoped, and no PRD-017, frontend,
  scheduler, PDF or XLSX scope is included.

## PRD-014 Dashboard v1 - 2026-08-08

### CLOSED after PR #22

- Merged into `master` via PR #22 at
  `04256eb0cb17e3d1fdb548edeae143578606d508`; final approved head:
  `8b836d7bb7b12fcf82ffb5bb8bbada4f3db758c6`.

- Added a tenant-scoped, read-only operational Dashboard at
  `GET /organizations/{organization_id}/dashboard` with optional bot and bounded
  period filters.
- Added SQL aggregate composition for Bots, Conversations, Human Handoff,
  Automation executions, Integration last-known state and Contacts without
  Dashboard tables, N+1 queries or ORM collection hydration.
- Reused the official PRD-015 resolver and the established PRD-005 compatibility
  boundary without duplicating business-hours, timezone or DST logic.
- Added `dashboard.read` for Viewer, Operator, Organization Admin, Organization
  Owner and explicitly scoped Platform Admin access.
- Responses contain safe counts/states only and exclude PII, secrets, domain
  payloads, write operations, health checks, automation execution and handoff
  claims.
- Closure preserves Dashboard as a read-only, non-Source-of-Truth projection
  without tables, migration, frontend or activity endpoint. Contacts remain
  organization-scoped; Integration health includes only active connections; the
  canonical PRD-015/PRD-005 boundary owns Business Hours resolution and no OAuth
  refresh or Business Hours write occurs.
- No migration was required; Alembic remains at `20260808_0016` and PRD-016
  Analytics & Reports remains NOT STARTED.
- Final validation: pytest 714 passed, 13 skipped, 2 warnings; focused PRD-014
  9 passed; PostgreSQL PRD-014 1 passed; performance sanity PASS with 10,000
  conversations; repository query budget 7 SELECTs O(1) for organization scope
  and 8 SELECTs O(1) for bot scope; mypy PASS across 387 source files; Ruff PASS;
  Black PASS across 387 files; `git diff --check` PASS; Alembic head
  `20260808_0016`.

## PRD-015 Business Hours & Holidays - 2026-08-08

### CLOSED after PR #18

- Merged into `master` via PR #18 at
  `025c3058388d51219e05fff1ae253a296238be89`; final feature head:
  `8831de5a3b284e8ba28d7d86ff983254b643c9b5`.
- Final validation: pytest 702 passed, 12 skipped, 2 warnings; PostgreSQL PRD-015
  3 passed; mypy PASS across 374 source files; Ruff PASS; Black PASS across 374
  files; `git diff --check` PASS; Alembic head `20260808_0016`.

- Added a provider-agnostic, tenant-scoped operational calendar with regular
  weekly schedules, date exceptions, holidays, partial closures, and manual
  overrides.
- Added deterministic `open`/`closed` resolution with explicit provenance,
  precedence, half-open boundaries, IANA timezone conversion, DST fold handling,
  and next known state change.
- Added lifecycle/RBAC administration, safe API errors, optimistic concurrency,
  durable idempotency receipts, transactional allowlisted audit, metrics, and
  structured logs.
- Added Alembic revision `20260808_0016`, local/API/regression tests, and real
  PostgreSQL constraint, tenant-isolation, lock, rollback, and migration-cycle
  tests.
- Added the explicit PRD-005 migration runbook and PRD-012 compatibility bridge:
  an applicable active PRD-015 calendar is authoritative, otherwise legacy
  PRD-005 behavior remains as a temporary fallback.
- Enforced one active organization default and one active calendar per bot to
  keep applicable-calendar selection deterministic under concurrency.
- PRD-014 Dashboard remains NOT STARTED, and no Google Calendar/OAuth adapter was
  added.

## PRD-013 Integration Management - 2026-08-07

### CLOSED after final security merge via PR #20

- Merged into `master` via PR #20 at
  `be52bbc49c6b34fc6b515e915564810068a74da3`; final review head:
  `beb3a6a01c5a983ab5d83a485f268dfc3202fa3b`.
- Final validation: pytest 705 passed, 12 skipped, 2 warnings; focused PRD-013
  39 passed; PostgreSQL PRD-013 1 passed; PRD-012/015 compatibility 18 passed;
  mypy PASS across 374 source files; Ruff PASS; Black PASS across 374 files;
  `git diff --check` PASS; Alembic head `20260808_0016`.
- Google real smoke remains `SKIPPED` because approved external credentials are
  unavailable. OAuth consent, callback, refresh, Calendar List and FreeBusy must
  pass before Google Calendar is enabled in staging or production. This is an
  operational external-enablement gate, not a blocker for PRD-013 closure.

- Added tenant-scoped Integration Management with lifecycle, RBAC, optional bot
  scope, safe health history and migration `20260807_0015`.
- Added encrypted/rotatable Google OAuth refresh credentials and signed,
  expiring, single-use OAuth state with replay protection.
- Added provider registry and real Google Calendar adapter for metadata and
  free/busy only, with explicit timeouts and safe error mapping.
- Added deterministic unit/API/OAuth/adapter tests, PostgreSQL smoke and optional
  explicit Google development smoke.
- Excludes event writes/sync, booking, CRM/ERP providers, generic HTTP, polling,
  Redis/Celery, Core Automation changes and PRD-014.

## PRD-012 Automation Management - 2026-08-07

### Closed

- Added durable, tenant-scoped Automation Management for the allowlisted
  `conversation.inbound_received -> request_handoff` flow.
- Validated PostgreSQL idempotency, leasing, two-worker concurrency, retries,
  terminal cleanup, RBAC, tenant isolation, and safe no-PII snapshots.
- Merged PR #14 into `master` with merge commit
  `924dc34e31e43504325d82d195ed7c31c71b1ca4`.
- Post-merge gates: 652 tests passed; mypy, Ruff, Black, and `git diff --check`
  passed; Alembic head is `20260807_0014`.
- PRD-013 remains NOT STARTED.

## PRD-011 Contacts and Customers (Contact increment) - 2026-08-06

### Added

- Tenant-scoped Contact identity with normalized WhatsApp identity, HMAC lookup,
  encryption at rest, inbound resolution, and `conversation.contact_id`.
- Administrative Contacts API with RBAC, sensitive/non-sensitive serialization,
  exact sensitive lookup, SQL pagination, lifecycle operations, and linked conversations.
- Explicit, idempotent batch backfill command with dry-run and safe aggregate metrics.

### Not Included

- Customer model, CRM, merge, anonymization, deletion, tags, import/export, and PRD-012.

## PRD-009 Conversations Management - 2026-07-30

### Added

- Extended the existing `conversation` and `message` tables for tenant/bot scoped
  administration without creating a parallel history source.
- Encrypted inbound/outbound administrative message records linked to receipts and
  outbound attempts.
- Administrative lifecycle `open`, `closed`, and `archived`, with documented
  inbound reopen behavior and archive protection.
- Paginated conversations/messages APIs and separate content-read permission.
- Alembic migration `20260730_0010` with scoped indexes and duplicate protection.

### Security

- Message text is encrypted at rest; managed `message.content` is empty.
- Lists return masked external identifiers; full text requires
  `conversation.read_content`.
- Logs exclude message content, ciphertext, raw payloads, secrets, and full
  external identifiers.

### Validated

- SQL repository lifecycle, encryption, deduplication, pagination, tenant
  isolation, and outbound status synchronization.
- Docker/PostgreSQL clean-volume migration, signed webhook flow, RBAC,
  direct ciphertext evidence, restart persistence, and Alembic cycle.

### Not Included

- PRD-010 Human Handoff, assignment, agent replies, queues, inbox UI, CRM,
  analytics, media processing, or administrative retry endpoints.

## PRD-008 WhatsApp Live Messaging - 2026-07-30

### Added

- Generic inbound/outbound channel contracts and a channel-neutral conversation
  handler that reuses the existing Conversation Core and bot-scoped Knowledge.
- Configured signed webhook processing for inbound text and delivery statuses.
- Durable inbound receipts and encrypted outbound delivery attempts.
- Deterministic long-message splitting, bounded persisted retry state, and
  monotonic provider status updates.
- Injectable fake and Meta-compatible WhatsApp Cloud API clients.
- Alembic migration `20260730_0009`.

### Security

- HMAC SHA-256 validation runs over raw bytes before JSON parsing.
- Webhook body and event counts are bounded.
- Tenant, bot, and configuration identity is checked throughout processing.
- Access tokens are decrypted only in memory; recipient and response text are
  encrypted at rest.
- Logs exclude raw payloads, text, full recipient IDs, secrets, signatures, and
  provider response bodies.

### Validated

- 31 focused PRD-008 tests.
- 603 tests passing with one upstream Starlette deprecation warning.
- Ruff, Black, and mypy clean across 286 source files.
- Docker/PostgreSQL clean-volume migration cycle with one head at
  `20260730_0009`.
- Signed inbound processing, Core/Knowledge execution, fake outbound delivery,
  sequential/concurrent deduplication, status ordering, encrypted persistence,
  safe logs, and API restart persistence.

### Compatibility

- No Core Engine or public conversation contract changed.
- Existing unscoped WhatsApp endpoints remain available for compatibility; the
  PRD-008 runtime uses the configured multi-tenant route.

### Not Included

- Real Meta validation, which requires approved external credentials.
- PRD-009 Conversations Management, PRD-010 Human Handoff, media processing,
  templates, frontend, or a distributed retry worker.

## PRD-007 WhatsApp Configuration - 2026-07-30

### Added

- Generic channel identity, resolved context, and resolver contracts.
- Tenant/bot-scoped WhatsApp channel configuration contracts, service, API,
  SQLAlchemy model, SQL/in-memory repositories, and lifecycle.
- Fernet authenticated secret encryption using environment-managed current and
  previous keys.
- Dedicated secret rotation with safe configuration flags.
- Direct SQL WhatsApp resolver by active phone number ID.
- Configuration-specific webhook challenge and HMAC SHA-256 validation routes.
- Resolver-to-Knowledge integration using explicit organization and bot context.
- Alembic migration `20260730_0008`.
- RBAC permissions for read, create, update, delete, activate, and rotate secrets.

### Security

- Secret plaintext and ciphertext are excluded from all output DTOs.
- Phone number ID and public webhook ID have global database uniqueness.
- Mutations use row locking; persistence conflicts roll back and return generic
  domain conflicts.
- Invalid webhook tokens/signatures return `403` without disclosing expectations.
- Uvicorn access logs redact the `hub.verify_token` query value.

### Validated

- 572 tests passing with one upstream Starlette deprecation warning.
- Ruff, Black, and mypy clean across 263 source files.
- Docker Compose API/PostgreSQL startup and Alembic
  upgrade/downgrade/upgrade with one head at `20260730_0008`.
- Encrypted DB persistence, restart survival, lifecycle, RBAC, multi-tenancy,
  SQL pagination, global uniqueness, resolver/provider identity, challenge, and
  HMAC validation.

### Not Included

- PRD-008, live message processing, outbound Meta calls, changes to
  `ConversationMessage`, Core Engine changes, templates, media, retries, or
  additional channel implementations.

## PRD-006 Knowledge Management - 2026-07-29

### Added

- Multi-tenant `KnowledgeEntry` contracts, service, repositories, and ORM model.
- Administrative API scoped by organization and bot.
- SQL-backed status/text filters, pagination, and total counts.
- Central RBAC permissions for knowledge read, create, update, delete, and publish.
- Isolated `BotKnowledgeProvider` for published entries with explicit tenant and bot scope.
- Alembic migration `20260729_0007_create_knowledge_entry_table.py`.
- Tests for contracts, service rules, rollback, repositories, API, RBAC,
  multi-tenancy, migration, pagination, filters, and provider isolation.

### Runtime Boundary

**BLOCKED RUNTIME INTEGRATION**

The conversation runtime currently does not resolve organization_id and bot_id.
The bot-scoped Knowledge provider is implemented and tested, but its runtime
connection to the Conversation Core is deferred to PRD-007 WhatsApp
Configuration, where bot-to-channel routing will establish that identity.

### Validated

- 557 tests passing with one upstream Starlette deprecation warning.
- Ruff, Black, and mypy clean across 239 source files.
- Clean-volume Docker Compose API/PostgreSQL startup.
- Alembic upgrade/downgrade/upgrade with one head at `20260729_0007`.
- Viewer, operator, owner, platform-admin, and cross-tenant behavior.
- Draft exclusion, published retrieval, archived exclusion, SQL filters, and pagination.
- Direct PostgreSQL constraints/indexes and persistence after API restart.

### Not Included

- PRD-007, bot-to-channel routing, changes to `ConversationMessage`, connection
  to `get_conversation_service()`, PDF/web ingestion, embeddings, vector search,
  external RAG, frontend, bulk import, analytics, or complex versioning.

## PRD-005 Business Configuration - 2026-07-29

### Added

- Business Configuration domain contracts and validation helpers.
- Structured `BusinessHours`, `BusinessService`, and `BusinessPolicy` contracts.
- PostgreSQL-backed `business_configuration` ORM model and repository.
- Alembic migration `20260728_0006_create_business_configuration_table.py`.
- Business Configuration API endpoints under `/bots/{bot_id}`.
- Business Configuration permissions in the central RBAC matrix.
- Tests for contracts, API behavior, migration metadata, RBAC, multi-tenancy, validation, persistence, and PRD regressions.

### Validated

- Docker Compose API/PostgreSQL runtime.
- Alembic upgrade/downgrade/upgrade for `20260728_0006`.
- Direct PostgreSQL Business Configuration persistence.
- Business Configuration persistence after API restart.
- Cross-tenant denial and platform-admin cross-organization access.
- Viewer/operator read-only behavior.
- Owner/admin write behavior.
- Structured validation for timezone, email, website, business hours, services, policies, payment methods, and handoff configuration.
- Core regression quality gates.

### Not Included

- PRD-006, Knowledge Sources, complex catalog, inventory, reservations, CRM integration, WhatsApp connection, automation execution, frontend, dashboard, billing.

## PRD-004 Bot Management - 2026-07-28

### Added

- Bot domain contracts and validation helpers.
- PostgreSQL-backed `bot` ORM model and repository.
- Alembic migration `20260728_0005_create_bot_table.py`.
- Bot API endpoints for create, list, read, update, activate, and deactivate.
- Bot permissions in the central RBAC matrix.
- Tests for bot contracts, API behavior, migration metadata, RBAC, multi-tenancy, and PRD regressions.

### Fixed

- Closed DB sessions for FastAPI service dependencies after each request, fixing SQLAlchemy pool exhaustion found during Docker smoke validation.

### Validated

- Docker Compose API/PostgreSQL runtime.
- Alembic upgrade/downgrade/upgrade for `20260728_0005`.
- Direct PostgreSQL bot persistence.
- Bot persistence after API restart.
- Tenant-scoped list/read/update behavior.
- Platform-admin global bot access.
- Slug uniqueness within tenant and same-slug allowance across tenants.
- Idempotent activation/deactivation.
- Inactive organization write blocking.
- Core regression quality gates.

### Not Included

- PRD-005, bot-to-WhatsApp-number routing, bot-specific Knowledge configuration, bot-specific Business configuration, billing, dashboard, frontend, onboarding, MFA, OAuth, SSO.

## PRD-003 Roles and Permissions - 2026-07-28

### Added

- Central roles and permissions domain.
- Role-permission matrix and reusable authorization helpers.
- `role` on User contracts and `app_user`.
- Alembic migration `20260728_0004_add_user_roles.py`.
- Protected Organizations and Users endpoints.
- Role and effective-permission endpoints.
- Tests for RBAC, multi-tenancy, role assignment, last-owner protection, and PRD-001/PRD-002 regressions.

### Validated

- Docker Compose API/PostgreSQL runtime.
- Alembic upgrade/downgrade/upgrade for `20260728_0004`.
- Direct PostgreSQL role persistence.
- Cross-tenant denial and platform-admin global access.
- Immediate permission effect after role changes.
- Core regression quality gates.

### Not Included

- PRD-004, custom roles, billing, dashboard, frontend, onboarding, MFA, OAuth, SSO.

## PRD-002 Authentication and Users - 2026-07-28

### Added

- User domain contracts and application service.
- Authentication application service.
- Argon2id password hashing through `argon2-cffi`.
- JWT access tokens through `PyJWT`.
- Reusable Bearer authentication dependency for FastAPI.
- PostgreSQL-backed `app_user` ORM model and repository.
- Alembic migration `20260728_0003_create_user_table.py`.
- Users and auth API endpoints.
- Unit, endpoint, auth, migration, and PRD-001 regression tests.

### Validated

- Docker Compose API/PostgreSQL runtime.
- Alembic upgrade/downgrade/upgrade for `20260728_0003`.
- Direct PostgreSQL persistence for users.
- Password hash is not plaintext.
- Login, `/auth/me`, password change, token invalidation, deactivation, and inactive-login rejection.
- API persistence after restart.
- Core regression quality gates.

### Not Included

- PRD-003, roles, granular permissions, invitations, password recovery, MFA, OAuth, SSO, billing, dashboard, frontend.

## PRD-001 Organizations - 2026-07-28

### Added

- Organization domain contracts and application service.
- PostgreSQL-backed Organization ORM model and repository.
- Alembic migration `20260728_0002_create_organization_table.py`.
- Organization API endpoints for create, list, get, update, and deactivate.
- Unit, endpoint, migration, and vertical-slice regression tests.

### Validated

- Docker Compose API/PostgreSQL runtime.
- Alembic upgrade/downgrade/upgrade for the new migration.
- PostgreSQL direct persistence and unique slug constraint.
- API persistence after restart.
- Core regression quality gates.

### Not Included

- Authentication, users, roles, billing, dashboard, frontend, PRD-002.

## core-v1.0.0 - 2026-07-28

### Status

- Closed Phase 2 as `Core v1.0.0 - Phase 2 Closed`.
- Prepared Phase 3 documentation without implementing Product Development features.

### Validated

- 470 tests passing.
- Ruff clean.
- Black clean.
- Mypy clean.
- Docker Compose build/start for API and PostgreSQL.
- Alembic migrations through `20260728_0001`.
- DB-backed conversation/message/state persistence.
- Persistence after API restart.
- Docker smoke tests for health, version, greeting, knowledge, support, and unknown flows.
- Integration Engine controlled errors/timeouts/retry tests inside Docker.

### Fixed

- Added missing Automation/Integration Alembic migration.
- Flushed persisted conversation creation before DB-backed state transitions.
- Declared `pytest-asyncio` in development dependencies for container test parity.

### Blocked

- WhatsApp real/live validation remains blocked pending external credentials or sandbox access.

## PRD-010 Human Handoff (CLOSED post-merge)

- Added scoped lifecycle, events, RBAC/tenancy checks, archive protection, and
  bot suppression/resume.
- Added encrypted, attributed, idempotent human replies linked to outbound attempts.
- Added migration `20260730_0011` and idempotency migration `20260730_0012`.
- Validated an isolated PostgreSQL Docker smoke without deleting the original volume.
