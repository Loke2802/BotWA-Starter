# PRD-022 — Observability v1

**Status:** IMPLEMENTED — PENDING CTO REVIEW

**Date:** 2026-08-15

**Alembic head:** `20260813_0022` (unchanged; no PRD-022 migration)

## Outcome

PRD-022 adds vendor-neutral operational observability to BotWA: request-scoped
correlation, safe structured JSON logs, application-scoped Prometheus metrics,
separate liveness/readiness endpoints, bounded provider and domain telemetry, and
standard command summaries. It adds no observability persistence and does not
make an external provider a global readiness dependency.

## Architecture

`ObservabilityRuntime` is created by each `create_app()` call and owns:

- one private Prometheus `CollectorRegistry`;
- the closed metric families registered in that registry;
- one isolated `DatabaseReadinessProbe` using a `NullPool` engine.

The runtime is stored on `app.state` and disposed by lifespan shutdown. No global
Prometheus default registry is used, so repeated app factories neither collide nor
share samples. Domain metric bridges use request context and are fail-open: an
observability failure never changes, commits, or rolls back business state.

## Correlation lifecycle

The outer ASGI observability middleware accepts `X-Correlation-ID` only when it is
a valid UUID. A missing or invalid value is replaced with a generated UUID. The
effective value is:

1. bound to a `ContextVar` and Structlog context;
2. exposed as `request.state.correlation_id`;
3. returned on every HTTP response as `X-Correlation-ID`;
4. reused by Audit drafts when callers do not supply an explicit correlation ID;
5. cleared in `finally`, including errors and concurrent requests.

Correlation IDs are never metric labels. One-shot commands create their own
ephemeral correlation UUID and do not persist it solely for observability.

## Structured logging

Application logs remain JSON on stdout/stderr with canonical bounded events. The
HTTP middleware emits one completion event for non-health/non-metrics requests and
one safe failure event for server errors. Unexpected exceptions use a closed
`error_code` and never log the exception string. Uvicorn's duplicate access logger
is disabled.

Logs introduced by this PRD contain no message body, webhook body, email, phone,
token, OAuth code/state, provider response, database URL, or free-form automation
error. Request-body rejection uses a bounded route classification rather than the
raw path. Existing secret-query filtering remains active.

## Prometheus endpoint and security

`GET /metrics` exposes only the app registry in Prometheus text format.

- `metrics_enabled=false` returns safe `404`.
- Enabled metrics require `Authorization: Bearer <dedicated-token>`.
- Comparison uses `hmac.compare_digest`.
- Missing or invalid credentials return generic `401` without echoing values.
- Production startup fails closed when the token is missing, weak, or reused from
  authentication, rate-limit, Audit cursor, or OAuth-state secrets.
- Successful scrapes are excluded from HTTP request metrics and INFO logs.

Token provisioning, TLS/network restriction, scrape configuration, deployment,
and rotation belong to PRD-023.

## HTTP metrics

The runtime exports:

- `botwa_http_server_requests_total{method,route,status_code}`;
- `botwa_http_server_request_duration_seconds{method,route,status_code}`.

Durations use `perf_counter` and shared buckets `0.005`, `0.01`, `0.025`, `0.05`,
`0.1`, `0.25`, `0.5`, `1`, `2.5`, `5`, and `10` seconds. Known endpoints use the
framework route template; pre-routing and unknown paths use `__unmatched__`. Raw
UUID paths are never labels. `/health`, `/health/live`, `/health/ready`, and
`/metrics` are excluded. Security behavior remains authoritative for `413`, `429`,
and invalid Host responses while correlation and bounded HTTP telemetry remain
available where middleware ordering permits.

## Provider telemetry

Real adapter call boundaries export:

- `botwa_provider_requests_total{provider,operation,result}`;
- `botwa_provider_request_duration_seconds{provider,operation,result}`;
- `botwa_provider_retries_total{provider,operation,result}` only for the existing
  Meta outbound retry flow.

Providers are closed to `meta`, `google_calendar`, and `mercado_pago`. Operations
are adapter-defined constants, never URLs or dynamic method names. Results are
closed to `success`, `timeout`, `network_error`, `rate_limited`, `auth_error`,
`provider_error`, `invalid_response`, and `rejected`. No external provider is
called by readiness or metrics scraping.

## Domain telemetry

The app-scoped registry bridges selected existing producers without deleting
their in-memory compatibility registries. Exported low-cardinality families cover:

- WhatsApp webhook and inbound/outbound message outcomes;
- normalized authentication and rate-limit decisions;
- Handoff request/claim/release/transfer/resolve/return-to-bot and bot suppression;
- Conversation create/message persistence/archive/reply;
- Automation claimed/completed/failed/skipped;
- Business Calendar open/closed/error resolution;
- Audit append/query and true-seconds query duration;
- Analytics operations and true histogram duration;
- Dashboard request outcome and true histogram duration;
- Plan operations without plan code;
- Billing operations, due transitions, signature rejection, and oversized bodies;
- Onboarding start/completion/readiness outcomes.

All label entry points validate closed values. Labels never contain Organization,
Bot, User, Conversation, Contact, correlation or provider-event identifiers,
email, phone, idempotency key, raw URL, raw exception, plan code, or secret.

## Health contracts

- `GET /health` remains compatible and returns `200 {"status":"ok"}`.
- `GET /health/live` reports process liveness only and always returns `200` while
  the app can serve the request, independent of DB/provider state.
- `GET /health/ready` performs only a bounded PostgreSQL `SELECT 1`; it returns
  `200 {"status":"ready"}` or `503` with a minimal database-unavailable payload.

The probe uses a separate `NullPool` engine. PostgreSQL receives a bounded connect
timeout plus statement timeout derived from `health_db_timeout_seconds`. Failures
are caught as SQLAlchemy errors and logged only as `database_readiness_failed`
with a safe code. The former lifespan HTTPBin integration checker is removed.
Tenant-specific integration health remains on-demand domain behavior and is not
global readiness.

## Command telemetry

Billing due transitions, Contacts backfill, and the Automation worker emit
`operation_started`, `operation_completed`, and safe `operation_failed` events.
Summaries expose only aggregate counts, dry-run where applicable, and monotonic
`duration_ms`. Existing return/exit semantics are preserved and no tenant or
resource identifier is logged.

## Failure semantics

- Metrics and logging are fail-open relative to business operations.
- Audit remains the fail-closed historical ledger and is not replaced by logs.
- A telemetry callback failure is swallowed at the observability boundary.
- DB-unavailable readiness fails closed to `not_ready` without affecting liveness.
- Provider outage affects only the calling domain, never global readiness.
- Metric scrape performs no database or provider call.
- No SQL query logging or observability table exists.

## Recommended alerts (PRD-023 handoff)

PRD-023 may create deployment-owned rules for DB readiness failure, HTTP 5xx ratio,
HTTP p95/p99, provider timeout/failure, invalid webhook surges, Billing retryable
due failures, stalled Automation workers, rate-limit persistence failure, and
production security startup failure. PRD-022 defines signals only; it does not
deploy alerts or notification integrations.

## Minimal runbooks

| Signal | Likely causes | First diagnostic actions |
|---|---|---|
| API unready by DB | network, credentials, saturation, PostgreSQL outage | check bounded readiness event, DB reachability and pool/service status; never print the URL |
| High HTTP 5xx | application defect or dependency failure | compare route templates/statuses and correlated safe error events; inspect the affected domain |
| Meta delivery failures | timeout, rate limit, auth or provider outage | compare Meta operation/result and retry counters; verify approved credentials out of logs |
| Google degradation | OAuth/auth, timeout or invalid response | inspect Google operation/result; run the approved live OAuth/Calendar gate before enablement |
| Mercado Pago due failures | provider outage/auth or stale commercial setup | inspect due summary and provider result; run sandbox reconciliation gates |
| Invalid webhook surge | bad signature, malformed/oversized traffic | compare webhook result and rate-limit counters; verify proxy/body limits and secrets securely |
| Rate-limit DB failure | PostgreSQL failure or contention | inspect persistence-error counter and readiness; verify DB health and indexed retention path |
| Automation worker stalled | scheduler/process outage or repeated failures | inspect batch start/completion cadence and execution outcomes; check worker process safely |

## Validation

- Focused PRD-022: **27 passed**.
- Affected-domain regression: **228 passed**.
- PostgreSQL readiness: **1 passed** with a real `SELECT 1`.
- Full pytest: **891 passed, 36 skipped, 2 warnings**.
- mypy: **PASS — 485 source files**.
- Ruff: **PASS**.
- Black: **PASS — 485 files**.
- `git diff --check`: **PASS**.
- Alembic: **`20260813_0022`**, one head.

External Meta, Google, and Mercado Pago live smokes are not closure gates for this
PRD and remain deployment enablement gates requiring approved credentials.

## Non-goals and PRD-023 boundary

PRD-022 explicitly does not add database tables/migrations, OpenTelemetry/OTLP,
Jaeger/Tempo, Prometheus or Grafana deployment, dashboard JSON, collectors,
Loki/ELK, vendor APM, alert deployment, paging/Slack/email automation, synthetic
monitoring, profiling/eBPF, business analytics, tenant observability UI, Audit
replacement, SQL logging, log files/rotation, provider reconciliation from health,
automatic migration, WebSockets, Kubernetes, CI/CD, deployment automation,
dependency scanning, retention, environment/instance deployment labels, or
PRD-023 implementation.

PRD-001 through PRD-021 remain **CLOSED**. PRD-023 remains **NOT STARTED**.
