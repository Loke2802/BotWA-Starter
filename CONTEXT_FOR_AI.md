# BotWA Starter - Context For AI Assistants

**Last updated:** 2026-08-15
**Project phase:** Phase 3 - PRD-001 through PRD-023 CLOSED; no next PRD defined
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
Dashboard is CLOSED after merge via PR #22 at
`04256eb0cb17e3d1fdb548edeae143578606d508`, with final approved head
`8b836d7bb7b12fcf82ffb5bb8bbada4f3db758c6`. PRD-016 Analytics & Reports is
CLOSED after PR #24 at merge commit
`601499071f39aad85dc4d9595fc04425f40a3962`, with final approved head
`6cafee11a0f807e07a9277eae98e128ab68aa711`. PRD-017 Audit Log is CLOSED after
PR #26 at merge commit `01c809c909360f4a31a6b26b1d4126a1c98e9c8b`, with final
approved head `3f7808da24d0dc1e3b5d6f3d337ee4562f5398b6`. PRD-018 Plans and Limits is
CLOSED after PR #28 at merge commit
`63f2fc79444e6b3f85b516b917860fb17fa8f779`, with final approved head
`2776a1b2ca6082142f14862c4eac4cf889eea631`. PRD-019 Billing & Subscriptions is
CLOSED after normal merge PR #30 at
`5a87ffc32be4315ebb6f9e64826bdb96f36ada58`, with final approved implementation
head `2a15b7f022c2989d73bb97d9b964495dba961778`. Canonical master for this closure
is `5a87ffc32be4315ebb6f9e64826bdb96f36ada58`. Billing is provider-agnostic and
Organization-scoped, with Mercado Pago and deterministic fake adapters, hosted
checkout, verified authoritative webhooks, transactional Plan/Audit application,
the four PRD-019 tables, and revision `20260812_0020`. Billing remains disabled by
default. A bounded one-shot due-transition job closes paid access and prepares
downgrades under an external deployment scheduler; manual reconcile is recovery
only. Commercial enablement remains BLOCKED as a separate operational gate, not a
code-closure blocker. PRD-020 Onboarding is CLOSED after merge via PR #32 at
`47b589df54282145ddce7b745ef208bb80321143`, with final approved head
`15564c245067952a74f19987370b6d5037de65a1`. It adds one minimal tenant-scoped
historical workflow row per Organization and
derives current readiness from operational Sources of Truth. It exposes
read/start/complete, closed typed steps and blockers, deterministic Bot selection,
Plan-driven applicability, same-transaction PRD-017 Audit, RBAC, concurrency
protection and revision `20260813_0021`. It does not duplicate CRUD, call external
providers, gate runtime or activate Billing. PRD-021 Security Hardening is CLOSED
after normal merge PR #34 at
`b4a9c3d682f88526f3fc9eef7ceb3d42c0d48981`, with final approved implementation
head `0eb2b6de48f3c86f0308c8d4933dcc4c2e382cc5`. It closes SEC-021-H01 through H06
with a
fail-closed production profile, legacy shutdown, normalized/rate-limited auth,
streaming body limits, inactive-Organization enforcement, concurrency-safe Owner
invariants, default 48-hour/200-row bounded rate-limit retention, sensitive Audit
expansion and Alembic `20260813_0022`. PRD-022 Observability is CLOSED after
normal merge PR #36 at `134b649ac058ec74c287f77e1825aae61ed4f8b1`, with final
approved implementation head `e261a4c5be1fde08d4da90f23cfbda4b9885174c`.
Its vendor-neutral operational boundary is request-scoped correlation, safe JSON
logs, app-scoped local Prometheus metrics with bounded cardinality, and separate
process liveness from PostgreSQL-only readiness. It adds no migration, table or
observability persistence, never makes external providers readiness dependencies,
and defers collectors, dashboards, alerts, retention and deployment to PRD-023.
PRD-023 CI/CD and Deployments v1 is CLOSED after normal merge PR #38 at
`71e18b33a09f8172e55a80f9ef34649717f6f9a5`, with final approved implementation
head `7980f800e0fd2d4cd7062ea5437d9dfe4fc4a504`. Trusted `master` run
`32426991892` passed `quality`, `tests`, `postgresql`, `container-security`, and
`publish-ghcr`, publishing
`ghcr.io/loke2802/botwa-starter:sha-71e18b33a09f8172e55a80f9ef34649717f6f9a5`
at digest
`sha256:a171325534235bcab094fbecf1378bf01455e59abb5c4b8895804430af899455`.
Its provider-neutral boundary includes hashed locks, PostgreSQL/Alembic CI, a
pinned non-root OCI image, safe build identity, trusted-master-only GHCR
publication, and deployment/recovery runbooks. No application migration was
added; Alembic remains one head at `20260813_0022`. Hosting remains NOT FROZEN
and no Luri staging or production application has been deployed. A pre-existing
GitHub Pages workflow deployment is accepted only as a non-production
repository/static-site deployment, not Luri hosting. Infrastructure decisions,
repository settings, credentials and real provider smokes remain external gates.

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
| `pytest` | 907 passed, 36 skipped, 1 warning |
| Focused PRD-023 | 16 passed |
| PostgreSQL CI matrix | 36 passed, 0 skipped |
| Dependency lock and vulnerability audit | PASS |
| Container smoke and Trivy HIGH/CRITICAL policy | PASS |
| `ruff check app tests` | All checks passed |
| `black --check app tests scripts` | 491 files would be left unchanged |
| `mypy app tests` | Success: no issues found in 486 source files |
| `git diff --check` | PASS |

## Infrastructure Validation

| Area | Result |
|---|---|
| Docker/PostgreSQL | PASS |
| Alembic migrations | PASS - `20260813_0022 (head)`, one head, PRD-021 PostgreSQL cycle validated |
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

PRD-001 through PRD-023 are CLOSED. No PRD-024 or next PRD is currently defined;
new work requires a new approved PRD or change scope.

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
| 14 | PRD-014 Dashboard | CLOSED |
| 15 | PRD-015 Business Hours & Holidays | CLOSED |
| 16 | PRD-016 Analytics & Reports | CLOSED |
| 17 | PRD-017 Audit Log | CLOSED |
| 18 | PRD-018 Plans and Limits | CLOSED |
| 19 | PRD-019 Billing & Subscriptions | CLOSED |
| 20 | PRD-020 Onboarding | CLOSED |
| 21 | PRD-021 Security Hardening | CLOSED |
| 22 | PRD-022 Observability | CLOSED |
| 23 | PRD-023 CI/CD and Deployments | CLOSED |

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
PRD-014 Dashboard is CLOSED after PR #22, merge commit
`04256eb0cb17e3d1fdb548edeae143578606d508`, final approved head
`8b836d7bb7b12fcf82ffb5bb8bbada4f3db758c6`. PRD-016 is CLOSED after PR #24,
merge commit `601499071f39aad85dc4d9595fc04425f40a3962`, final approved head
`6cafee11a0f807e07a9277eae98e128ab68aa711`; PRD-017 is CLOSED after PR #26,
merge commit `01c809c909360f4a31a6b26b1d4126a1c98e9c8b`, final approved head
`3f7808da24d0dc1e3b5d6f3d337ee4562f5398b6`. PRD-018 is CLOSED after PR #28,
merge commit `63f2fc79444e6b3f85b516b917860fb17fa8f779`, final approved head
`2776a1b2ca6082142f14862c4eac4cf889eea631`. PRD-019 is CLOSED after normal merge
PR #30, merge commit `5a87ffc32be4315ebb6f9e64826bdb96f36ada58`, final approved
implementation head `2a15b7f022c2989d73bb97d9b964495dba961778`. PRD-020 is
CLOSED after PR #32 at `47b589df54282145ddce7b745ef208bb80321143`, final approved
head `15564c245067952a74f19987370b6d5037de65a1`. PRD-021 is CLOSED after PR #34;
PRD-022 is CLOSED after normal merge PR #36 at
`134b649ac058ec74c287f77e1825aae61ed4f8b1`, final approved implementation head
`e261a4c5be1fde08d4da90f23cfbda4b9885174c`; PRD-023 is CLOSED after normal
merge PR #38 at `71e18b33a09f8172e55a80f9ef34649717f6f9a5`, final approved
implementation head `7980f800e0fd2d4cd7062ea5437d9dfe4fc4a504`, and trusted
`master` run `32426991892`. No next PRD is currently defined.
Billing commercial enablement remains BLOCKED pending
approved configuration and the real Mercado Pago sandbox smoke.
