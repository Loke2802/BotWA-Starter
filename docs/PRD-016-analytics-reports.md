# PRD-016 — Analytics & Reports v1

**Status:** IMPLEMENTED — PENDING CTO REVIEW
**Date:** 2026-08-08
**Alembic revision:** `20260808_0017`

## Purpose

PRD-016 provides tenant-scoped historical analytics on PostgreSQL. It derives
facts from operational Sources of Truth, projects them into a rebuildable daily
read model, aggregates bounded historical ranges, compares the immediately
previous period, and exports aggregate CSV without PII.

Analytics derives, projects, aggregates, and rebuilds. It does not replace a
Source of Truth, govern an operational domain, mutate data from GET, or invent
history that the operational schema did not retain.

## Scope

- Append-only Conversation Management transition events.
- Non-reusable historical Human Handoff lifecycle rows.
- Daily bot-scoped and organization-scoped projections.
- Deterministic `rebuild_day` and `rebuild_range` application services.
- Read-only day, ISO-week, and calendar-month analytics.
- Equal-duration `previous_period` comparison.
- Aggregate CSV export.
- Tenant isolation, RBAC, safe errors, metrics, and structured logs.
- PostgreSQL partial uniqueness and concurrent UPSERT validation.

## Non-goals

No frontend, PDF, XLSX, scheduled reports, report jobs, background queue,
Celery, Redis, Kafka, warehouse, ClickHouse, BigQuery, Snowflake, Redshift,
Airflow, dbt, forecasting, AI insights, natural-language analytics, funnels,
cohorts, custom dimensions, BI builder, CRM/customer analytics, realtime
streaming, delivery by email/WhatsApp, or PRD-017 functionality is included.

## Operational Sources of Truth

| Metric | Canonical source and timestamp |
|---|---|
| Conversations started | `Conversation.started_at` |
| Conversations closed | `conversation_management_event.to_status = closed` at `occurred_at` |
| Handoffs created | `handoff_cycle.requested_at` |
| Handoffs resolved | `handoff_cycle.resolved_at` |
| Handoff duration | `resolved_at - requested_at` for valid resolved cycles |
| Automation executions created | execution `created_at`, once per execution id |
| Automation terminal outcome | current terminal status at `completed_at` |
| Contacts created | organization-scoped `Contact.created_at` |

`updated_at`, Conversation Core state history, `ended_at`, automation
`attempt_count`, and receipt occurrence time are not substituted for these
business timestamps.

## Conversation Management history

`conversation_management_event` is a pure append-only, tenant-scoped event
ledger. It records the existing allowed transitions (`open → closed`,
`closed → open`, `open → archived`, and `closed → archived`) in the same
transaction as the `management_status` change. User transitions retain the
actor; inbound auto-reopen is a system transition correlated to the inbound
receipt. Delayed provider timestamps do not backdate the administrative
transition.

There is no public update/delete API. Transaction rollback reverts both status
and event, preventing either side from being committed alone.

## Human Handoff history

`handoff_session` remains the current operational state. `handoff_cycle` is a
separate historical lifecycle row created for every new accepted request and is
never reused for a later cycle. `activated_at` and `resolved_at` are completed
monotonically within that same row and transaction.

Both normal resolution and `return_to_bot` terminate a cycle and count as a
resolved handoff; `return_to_bot` is not interpreted as customer success.
Idempotent retries of an already-active request remain conflicts and do not
create duplicate cycles.

## Automation retry semantics

`automation_executions_created` counts each execution once at `created_at`.
Terminal counts represent the execution's current terminal status at
`completed_at`; `attempt_count` is never counted. A later rebuild corrects a
failed execution that is retried and succeeds, including relocating the current
outcome when `completed_at` changes. Intermediate failed attempts are not an
analytics ledger in v1.

## Historical coverage boundary

The two new historical sources begin with PRD-016. The implementation does not
fabricate pre-PRD-016 closure transitions or handoff cycles. Conversation starts
and Contact creation can be rebuilt from their exact existing timestamps;
historical closures and handoff cycles before the ledgers are not completely
reconstructible.

## Reporting timezone and DST

All organization and bot rows use one reporting timezone:
`Organization.settings.timezone`, falling back to
`DEFAULT_ORGANIZATION_TIMEZONE` (`America/Lima`). `Bot.timezone` is deliberately
not used for analytics buckets.

Each row stores the reporting timezone used. A daily bucket is the half-open
interval from local midnight to the following local midnight converted to UTC;
no 24-hour assumption is made, so 23-hour and 25-hour DST days are supported.
Because organization timezone has no effective-dated history, a historical
rebuild uses the timezone effective when that rebuild runs. Rows produced under
an older timezone are incomplete until rebuilt.

## Daily read model and grain

`analytics_daily_summary` stores nonnegative `BIGINT` counts and sums, plus
`source_watermark_at`, `computed_at`, and lifecycle timestamps.

- Bot row: `(organization_id, bot_id, local_date)` for Conversation, Handoff,
  and Automation metrics.
- Organization row: `(organization_id, bot_id NULL, local_date)` for Contacts
  only.

PostgreSQL partial unique indexes separately enforce both grains. Organization
totals sum bot rows and read Contacts only from the `bot_id NULL` row; Contacts
are never distributed to bots or double-counted.

## Rebuild semantics

`rebuild_day(organization_id, bot_id, local_date)` resolves the canonical
timezone, derives the UTC interval, captures `source_watermark_at`, runs a fixed
number of aggregate SQL queries, and performs a PostgreSQL
`INSERT … ON CONFLICT DO UPDATE`. `bot_id=None` computes only Contacts; a bot id
computes only bot-scoped metrics.

The projection recalculates and replaces every value; it never applies deltas.
Repeated rebuilds therefore preserve counts when Sources of Truth are unchanged.
Concurrent rebuilds of the same grain converge to one row. A zero-event day is
still written, distinguishing calculated zero from missing coverage.

`rebuild_range` processes every day in `[from_local_date,to_local_date)`, permits
exactly 366 days, and rejects larger ranges. It is an internal application/admin
boundary: there is no public rebuild permission, startup rebuild, scheduler, or
background queue.

## Source watermark

Every rebuild captures one UTC watermark at its start. Source queries constrain
the relevant business timestamp to `< source_watermark_at`, avoiding a mix of
facts that arrive after the operation begins. `computed_at` records completion;
v1 does not attempt a global serializable snapshot.

## Read API

`GET /organizations/{organization_id}/analytics` accepts local date filters
`from` and `to` with `[from,to)` semantics, optional `bot_id`, `group_by` of
`day|week|month`, and optional `compare=previous_period`. The maximum range is
366 days.

The GET reads only `analytics_daily_summary`; it does not call operational
services, rebuild, write, commit, or create audit events. Weekly and monthly
buckets are derived from daily rows. Handoff average uses total seconds divided
by total resolved count, never an average of averages. Automation success rate
is `succeeded / (succeeded + failed)` and is null for a zero denominator.

Completeness requires every expected bot row plus the organization Contacts row
for every requested date and current reporting timezone. Missing rows remain
visible as `complete=false`; GET never fills gaps.

## Previous-period comparison

`previous_period` uses the immediately preceding local-date range with equal
duration. Each comparable metric returns current, previous, absolute change, and
percent change. Previous zero/current zero yields `0`; previous zero/current
positive yields `null`, never Infinity or NaN.

## CSV export

`GET /organizations/{organization_id}/analytics/export?format=csv` uses the same
read model, grouping, and calculations as the JSON API. It rejects incomplete
coverage with `409 ANALYTICS_DATA_INCOMPLETE` and never queries operational
Sources of Truth directly.

CSV contains aggregate periods and approved metrics only. It excludes names,
phone numbers, email, messages, entity ids, external identifiers, ciphertext,
tokens, secrets, authorization data, and provider payloads.

## RBAC and tenant isolation

- Viewer and Operator: `analytics.read`.
- Organization Admin and Owner: `analytics.read`, `analytics.export`.
- Platform Admin: the same permissions with explicit organization scope.
- Rebuild: no public permission or endpoint.

Every query filters `organization_id`; bot paths also verify
`organization_id + bot_id`. A cross-tenant bot returns a safe not-found result.
Ledgers and projections carry tenant identity, and observability labels never
contain tenant, bot, or user ids.

## Safe errors and observability

The allowlisted error codes are `ANALYTICS_INVALID_RANGE`,
`ANALYTICS_RANGE_TOO_LARGE`, `ANALYTICS_INVALID_GROUPING`,
`ANALYTICS_DATA_INCOMPLETE`, `ANALYTICS_NOT_FOUND`, `ANALYTICS_FORBIDDEN`, and
`ANALYTICS_UNAVAILABLE`. Responses do not expose SQL, stack traces, table names,
tenant ids, or payloads.

Low-cardinality metrics cover requests, query duration, projection rebuilds,
rebuild duration/errors, and exports with allowlisted operation/result/grouping
dimensions. Structured logs contain no PII.

## PostgreSQL and testing strategy

Revision `20260808_0017` creates only `conversation_management_event`,
`handoff_cycle`, and `analytics_daily_summary`, with one Alembic head. Validation
covers partial uniqueness, zero rows, deterministic UPSERT, two-thread
concurrency, tenant/bot isolation, transaction rollback, handoff lifecycle
persistence, DST boundaries, leap-year limits, completeness, grouping, weighted
averages, retry correction, previous period, RBAC, read-only GET, and CSV without
PII. The migration is exercised through upgrade, downgrade to `0016`, and
re-upgrade to `0017` on PostgreSQL.

## PRD-017 boundary

PRD-017 remains NOT STARTED. PRD-016 creates no general audit-log product,
report jobs, scheduler, delivery mechanism, or unrelated future infrastructure.

## Final validation

- Focused PRD-016 plus Conversation/Handoff regression: 29 passed.
- PostgreSQL PRD-016: 2 passed.
- Full pytest: 721 passed, 15 skipped, 2 warnings.
- mypy: PASS — 400 source files.
- Ruff: PASS.
- Black: PASS — 400 files.
- `git diff --check`: PASS.
- Alembic head: `20260808_0017`.
- PostgreSQL migration cycle `0016 → 0017 → 0016 → 0017`: PASS.
