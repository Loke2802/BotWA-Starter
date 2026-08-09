# PRD-014 Dashboard v1

**Status:** CLOSED
**Initial master:** `c7088ae5d7ff492254536685891a0ef95c003b2c`
**Merged via:** PR #22
**Merge commit:** `04256eb0cb17e3d1fdb548edeae143578606d508`
**Final approved head:** `8b836d7bb7b12fcf82ffb5bb8bbada4f3db758c6`
**Alembic head:** `20260808_0016`

## Scope

PRD-014 provides a tenant-scoped, read-only operational Dashboard API. It reads,
aggregates and composes existing Sources of Truth without governing, copying or
synchronizing them. The v1 response contains safe counts and states for bots,
conversations, Human Handoff, Automation Management, Integration Management,
Contacts and Business Hours.

Dashboard is not a Source of Truth and does not own persistence. It creates no
Dashboard tables, snapshots, reporting subsystem or cache.

## Non-goals

- frontend, React or configurable widgets;
- advanced analytics, reports, exports, BI, forecasting, funnels or cohorts;
- alerts, notifications, WebSockets, SSE or streaming;
- Redis, distributed cache, Celery, warehouse or materialized reporting data;
- write-side operations, audit events or domain lifecycle changes;
- PRD-016 Analytics & Reports or PRD-017 Audit Log.

The optional activity endpoint is intentionally excluded from v1. Adding a time
series without a reporting boundary would overlap PRD-016; the summary endpoint
already covers the approved operational scope.

## Sources of Truth

| Dashboard section | Source of Truth |
|---|---|
| Organization/timezone | Organization Management canonical settings |
| Bots | Bot Management |
| Conversations | Conversation Management product-scoped rows |
| Human Handoff | PRD-010 handoff sessions |
| Automations | PRD-012 durable executions and receipts |
| Integrations | PRD-013 connections and last persisted health state |
| Contacts | PRD-011 Contacts |
| Business | PRD-015 official resolver; PRD-005 fallback only through the existing compatibility contract |

Dashboard never calls Google, refreshes OAuth, runs integration health checks,
executes automations, claims handoffs, changes business-hours state or returns
domain payloads.

## Query architecture

`DashboardQueryService` composes `SqlAlchemyDashboardRepository` with
`DashboardBusinessStatusReader`. The repository issues fixed SQL aggregate
queries using `COUNT ... FILTER`, `MIN` and scoped joins. It does not load ORM
collections, count rows in Python, query per bot in a loop or call internal HTTP
endpoints.

The Business reader delegates precedence, exceptions, holidays, overrides,
timezone and DST to the PRD-015 resolver. When a bot has no applicable PRD-015
calendar, it uses the established PRD-005 compatibility service. Organization
scope resolves only the active organization-default PRD-015 calendar; without
one the safe state is `unknown`.

## API and period semantics

`GET /organizations/{organization_id}/dashboard`

Filters:

- `bot_id=<uuid>` is optional;
- `period=today|last_7_days|last_30_days`;
- or the explicit timezone-aware pair `from` and `to`;
- preset periods use local calendar-day boundaries in the canonical organization
  timezone, or bot timezone when `bot_id` is present;
- organization settings without an explicit timezone use the canonical
  `OrganizationSettings` default, `America/Lima`; Dashboard does not define an
  independent fallback;
- every interval is `[from, to)` and explicit ranges cannot exceed 90 days;
- the explicit-range limit is exactly 90 times 24 elapsed hours after UTC
  normalization (not 90 local calendar days); exactly 90 days is accepted;
- presets and explicit ranges cannot be mixed.

Safe error codes are `DASHBOARD_INVALID_RANGE`, `DASHBOARD_RANGE_TOO_LARGE`,
`DASHBOARD_INVALID_FILTER`, `DASHBOARD_NOT_FOUND`, `DASHBOARD_FORBIDDEN` and
`DASHBOARD_UNAVAILABLE`.

## Response and metric semantics

`DashboardSummaryResponse` contains `organization_id`, optional `bot_id`, the
resolved period, `generated_at`, and these sections:

- `business`: canonical `open`, `closed` or `unknown`, safe source and optional
  `next_change_at`;
- `bots`: `active` and `inactive` are the complete canonical Bot lifecycle;
  therefore `total = active + inactive`;
- `conversations`: `open`, `closed` and `archived` are the complete canonical
  Conversation Management lifecycle and `total` is their sum. Legacy Core rows
  whose product `management_status` is null are intentionally outside this
  product-scoped read model;
- `handoffs`: `human_active` as active, `waiting_human` as pending, creations and
  resolutions in period, plus age of the oldest waiting/active request;
- `automations`: period execution counts for pending, running, succeeded, failed,
  skipped and cancelled real states;
- `integrations`: `total` includes every current connection lifecycle (`draft`,
  `active`, `inactive`, `archived`), while the persisted health breakdown covers
  only `active` connections. Thus `active = healthy + degraded + unreachable +
  auth_error + unknown`; inactive states cannot create operational alerts;
- `contacts`: organization-wide total and creations in period.

With `bot_id`, bots, conversations, handoffs, automations, integrations and
business are bot-scoped. Contacts remain explicitly `organization` scoped because
Contacts has no canonical bot ownership; the API never silently attributes them
to a bot.

## RBAC and tenant isolation

PRD-014 adds only `dashboard.read`. Viewer, Operator, Organization Admin and
Organization Owner receive it. Platform Admin may use it only with the explicit
organization path. There are no Dashboard write or activity permissions.

Every aggregate filters `organization_id`; bot-capable aggregates additionally
filter the validated same-tenant `bot_id`. A missing or cross-tenant bot returns a
safe 404 and is never counted. There is no global Dashboard route.

## PII and read-only policy

The response exposes counts, safe enums, context UUIDs and timestamps only. It
contains no messages, body/text, phone, email, sender, display name, notes,
external customer IDs, ciphertext, hashes, tokens, secrets, authorization data,
provider payloads or raw external data.

Dashboard code and its PRD-015/PRD-005 read dependencies perform no
`session.add`, `session.delete`, `commit`, update statement, audit write or
idempotency receipt during a GET. A query does not update last-seen state or
trigger any domain action. `generated_at` communicates the read-side composition
time; no global serializable snapshot or domain locking is attempted.

## Performance and observability

The repository uses one fixed aggregate query per section, regardless of tenant
row count. Organization scope has a fixed budget of seven repository SELECTs:
one organization scope lookup plus six aggregates. Bot scope has eight: the
organization lookup, a same-tenant bot lookup and the same six aggregates. The
performance test loads 10,000 conversations and proves both budgets remain O(1),
with a single SQL `COUNT` query for conversations and no selected ORM identity
columns.

PRD-015/PRD-005 Business Hours resolution is outside that repository budget and
has its own read-query cost depending on whether an applicable calendar or the
legacy fallback is used. Consequently, PRD-014 does not claim that the complete
HTTP request always executes seven SQL statements. Neither boundary queries per
bot or hydrates Dashboard collections.

Existing tenant/status indexes support the v1 access paths. No speculative index
or migration was added: the implementation introduces no table and retains the
single Alembic head `20260808_0016`. PostgreSQL validation also confirms there is
no table whose name begins with `dashboard`.

Low-cardinality internal metrics record request totals, accumulated duration and
query errors with only `endpoint` and `result` labels. Structured Dashboard logs
contain the same safe labels and no tenant, bot or user identifiers.

## Closed architectural decisions

- Dashboard is read-only and is not a Source of Truth.
- It owns no tables or migration and has no frontend or activity endpoint.
- It does not advance PRD-016 Analytics & Reports.
- It does not execute health checks, refresh OAuth, execute automations, claim
  handoffs or modify Business Hours.
- Contacts remain organization-scoped because they have no canonical bot
  ownership.
- Integration health breakdown includes only active integrations.
- Business status remains delegated to the canonical PRD-015 resolver and PRD-005
  compatibility boundary.
- Responses contain no PII or provider secrets.

## Validation strategy

Automated coverage includes empty and populated summaries, all period presets,
custom ranges, `[from, to)`, the 90-day limit, IANA timezone/DST behavior,
same-tenant and cross-tenant bot filters, all aggregate sections, PRD-015
resolution, indirect PRD-005 fallback, all approved RBAC roles, Platform Admin
explicit organization scope, PII absence, no DB side effects, SQL aggregate
performance, safe persistence errors and real PostgreSQL tenant isolation.

Final validation:

- focused PRD-014: 9 passed;
- PostgreSQL PRD-014: 1 passed;
- performance sanity with 10,000 conversations: PASS;
- repository query budget: 7 SELECTs O(1) for organization scope and 8 SELECTs
  O(1) for bot scope;
- full pytest: 714 passed, 13 skipped, 2 warnings;
- mypy: PASS, 387 source files;
- Ruff: PASS;
- Black: PASS, 387 files;
- `git diff --check`: PASS;
- Alembic head: `20260808_0016`.

PRD-001 through PRD-016 are CLOSED. PRD-017 and later increments remain NOT
STARTED.
