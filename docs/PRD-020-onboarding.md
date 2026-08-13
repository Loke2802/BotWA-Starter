# PRD-020 — Onboarding v1

**Status:** IMPLEMENTED — PENDING CTO REVIEW

**Date:** 2026-08-13

**Alembic revision:** `20260813_0021`

## Scope and architecture

PRD-020 implements a tenant-scoped onboarding workflow without duplicating the
administrative CRUD of existing resources. The architecture is:

`Operational Sources of Truth → OnboardingReadinessService → OnboardingService → API`

Current readiness is always derived from operational Sources of Truth. Only the
minimal historical workflow (`in_progress` or `completed`) is persisted. A missing
workflow row means `not_started`; it is not an error and does not prevent an
existing Organization from operating.

## Persistence model

Migration `20260813_0021` creates only `organization_onboarding`, with one row per
Organization. It stores the Organization primary/foreign key, workflow status,
start/completion actors and timestamps, optimistic `version`, and audit timestamps.
Database constraints enforce the closed statuses, positive versions, consistent
completion fields, and chronological completion. There is no JSON, step table,
readiness cache, backfill, PII, or invented historical event.

The row is created lazily by `start`; Organization creation remains unchanged.
The write lock order is Organization row first, then onboarding row. This
serializes concurrent starts/completions and keeps the workflow and PRD-017 Audit
event in the same transaction.

## Readiness and steps

The visible, ordered catalog is:

1. `organization_profile` — required; existing Organization contract and active status.
2. `owner_ready` — required; at least one active Organization Owner.
3. `initial_bot` — required; an active tenant Bot.
4. `business_configuration` — required for the selected Bot and validated by the existing contract.
5. `whatsapp` — conditional; required only when the Plan feature is enabled.
6. `knowledge` — optional when enabled by Plan.
7. `integrations` — optional when enabled by Plan.
8. `review` — synthetic; ready when all blocking requirements are ready.

The current PRD-018 Plan assignment and active Plan are an internal completion
requirement but not a visible step. WhatsApp `setup_ready` is derived only from
persisted active configuration and internal inbound/outbound prerequisites; there
is no webhook challenge, message, provider request, or secret readback. Live
validation remains `pending` or `unknown` unless durable evidence exists.

Knowledge is ready with at least one published entry for the selected Bot, but is
never a completion blocker. Integrations are ready with an active configured
connection, but are also optional; persisted last-known health is used only for
`external_validation`. GET and completion perform no remote health check.
BusinessCalendar is not a separate step and never blocks v1. Human Handoff,
Automations, Contacts, Analytics, Dashboard, Billing, and Business Hours are not
added to the catalog.

The initial Bot selector is deterministic: it loads active candidates ordered by
`created_at` and `id`, validates each BusinessConfiguration with the existing
domain contract, and selects the first valid `configured` candidate. If none is
ready-configured, it selects the first active candidate in the same deterministic
order. A merely existing, invalid, or non-configured row has no priority; inactive
and cross-tenant Bots cannot participate. No resource is mutated by onboarding.

Before historical completion, readiness is `ready` only when completion
requirements are met, otherwise `not_ready`. After completion, the historical
status remains `completed`; later resource regression changes current readiness
to `degraded` without reopening the workflow.

## API, authorization, and errors

- `GET /organizations/{organization_id}/onboarding`
- `POST /organizations/{organization_id}/onboarding/start`
- `POST /organizations/{organization_id}/onboarding/complete`

GET is read-only and returns workflow plus freshly derived readiness. Start is a
lazy idempotent transition to `in_progress` at version 1. Complete requires a
positive `expected_version`, recomputes readiness under locks, and advances once
to `completed` at version 2. Repeated start/completed requests are safe no-ops and
do not emit duplicate Audit events. Each no-op computes its response while the
Session state is valid and then commits the read-only transaction before returning,
releasing Organization/workflow locks without changing version or timestamps.

`onboarding.read` and `onboarding.manage` are granted to Organization Owner and
Organization Admin; Operator and Viewer have neither. Platform Admin remains
explicitly Organization-scoped. Repository queries and referenced resources are
always tenant-scoped; there is no global listing.

Typed errors cover missing Organization, forbidden access, not started, not ready
with closed blocker codes, version conflict, unavailable persistence/Audit, and
invalid requests. Responses expose typed closed DTOs, safe resource references,
action hints, flags, and reason codes only—never PII, credentials, ciphertext, or
external WhatsApp identifiers.

## Audit and observability

Effective transitions append `onboarding.started` or `onboarding.completed` via
the mandatory fail-closed AuditWriter in the same Session and transaction. Typed
metadata contains only workflow version and required-step counts. Audit failure
rolls back the workflow mutation. No-op reads/transitions and blocked completion
attempts do not fabricate resource or success Audit events.

Metrics use bounded result labels for starts, completion attempts, and readiness
reads. Structured logs record started, completed, and blocked events without PII,
secrets, tenant IDs, user IDs, or resource IDs.

## Boundaries and compatibility

Onboarding reads Plan applicability but never bypasses PRD-018 enforcement; all
resource mutations still go through their existing services and permissions. It
does not call Billing, alter Plan assignment, enable commercial Billing, provision
providers, or introduce provider-specific data. It does not gate Bots, WhatsApp,
Conversations, Handoff, Knowledge, or Integration runtimes. Existing and new
Organizations have no automatic onboarding row.

External WhatsApp/Google/Mercado Pago validation remains outside request-time
onboarding. Business resource mutations that predate fail-closed generic Audit are
not retroactively changed or fabricated by PRD-020.

## Validation

- Focused PRD-020 unit/API: 22 passed.
- Real PostgreSQL PRD-020: 3 passed.
- Affected-domain regression: 123 passed.
- PostgreSQL migration cycle `0020 → 0021 → 0020 → 0021`: PASS.
- Full pytest: 843 passed, 29 skipped, 2 warnings.
- mypy: PASS — 463 source files.
- Ruff: PASS.
- Black: PASS — 463 files.
- `git diff --check`: PASS.
- Alembic: one head, `20260813_0021`.

## Explicit exclusions

No frontend or wizard UI, templates, invitations, onboarding email/verification,
sample data, CRM import, industry rules, Billing activation/pricing/checkout,
live provider provisioning, Analytics funnel, scheduler, or PRD-021/022/023 work.
PRD-021 remains NOT STARTED.
