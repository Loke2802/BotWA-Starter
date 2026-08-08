# PRD-014 Dashboard v1

**Status:** IMPLEMENTED - PENDING CTO REVIEW
**Initial master:** `c7088ae5d7ff492254536685891a0ef95c003b2c`
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
- every interval is `[from, to)` and explicit ranges cannot exceed 90 days;
- presets and explicit ranges cannot be mixed.

Safe error codes are `DASHBOARD_INVALID_RANGE`, `DASHBOARD_RANGE_TOO_LARGE`,
`DASHBOARD_INVALID_FILTER`, `DASHBOARD_NOT_FOUND`, `DASHBOARD_FORBIDDEN` and
`DASHBOARD_UNAVAILABLE`.

## Response and metric semantics

`DashboardSummaryResponse` contains `organization_id`, optional `bot_id`, the
resolved period, `generated_at`, and these sections:

- `business`: canonical `open`, `closed` or `unknown`, safe source and optional
  `next_change_at`;
- `bots`: total, active and inactive current bot lifecycle counts;
- `conversations`: total/open/closed/archived plus starts in the selected period;
- `handoffs`: `human_active` as active, `waiting_human` as pending, creations and
  resolutions in period, plus age of the oldest waiting/active request;
- `automations`: period execution counts for pending, running, succeeded, failed,
  skipped and cancelled real states;
- `integrations`: current total/lifecycle count and last persisted health states
  healthy, degraded, unreachable, auth_error and unknown;
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

Dashboard code has no `session.add`, `session.delete`, `commit`, update statement
or audit write. A query does not update last-seen state or trigger any domain
action. `generated_at` communicates the read-side composition time; no global
serializable snapshot or domain locking is attempted.

## Performance and observability

The repository uses one fixed aggregate query per section, regardless of tenant
row count. The performance test loads 10,000 conversations and proves a single
SQL `COUNT` query handles that section with a fixed seven-query repository budget
for an organization summary. No ORM conversation identity columns are selected.

Existing tenant/status indexes support the v1 access paths. No speculative index
or migration was added: the implementation introduces no table and retains the
single Alembic head `20260808_0016`. PostgreSQL validation also confirms there is
no table whose name begins with `dashboard`.

Low-cardinality internal metrics record request totals, accumulated duration and
query errors with only `endpoint` and `result` labels. Structured Dashboard logs
contain the same safe labels and no tenant, bot or user identifiers.

## Validation strategy

Automated coverage includes empty and populated summaries, all period presets,
custom ranges, `[from, to)`, the 90-day limit, IANA timezone/DST behavior,
same-tenant and cross-tenant bot filters, all aggregate sections, PRD-015
resolution, indirect PRD-005 fallback, all approved RBAC roles, Platform Admin
explicit organization scope, PII absence, no DB side effects, SQL aggregate
performance and real PostgreSQL tenant isolation.

Final validation:

- local PRD-014: 5 passed;
- PostgreSQL PRD-014: 1 passed;
- performance sanity with 10,000 conversations: PASS;
- full pytest: 710 passed, 13 skipped, 2 warnings;
- mypy: PASS, 387 source files;
- Ruff: PASS;
- Black: PASS, 387 files;
- `git diff --check`: PASS;
- Alembic head: `20260808_0016`.

PRD-001 through PRD-013 remain CLOSED. PRD-015 remains CLOSED. PRD-016 and later
increments remain NOT STARTED.
