# PRD-021 — Security Hardening v1

**Status:** CLOSED
**Date:** 2026-08-13
**Alembic head:** `20260813_0022`

## Closure record

- Implementation PR: #34.
- Implementation merge: `b4a9c3d682f88526f3fc9eef7ceb3d42c0d48981`.
- Final approved implementation head:
  `0eb2b6de48f3c86f0308c8d4933dcc4c2e382cc5`.
- Merge method: normal merge commit.
- Migration: `20260813_0022_security_hardening.py`; Alembic has one head at
  `20260813_0022`.

PRD-021 Security Hardening v1 is closed as a fail-closed backend production
security profile. Deployment-only provider, credential, TLS, proxy, MFA-decision,
dependency-scanning and release gates remain operational prerequisites and do
not reopen this code closure.

## Objective and threat model

PRD-021 closes the production-facing attack paths confirmed during technical
discovery: unsafe deployment defaults, anonymous legacy mutation routes,
credential enumeration and brute force, public bootstrap races, and continued
tenant access after Organization deactivation. The threat model covers hostile
Internet clients, forged and oversized provider callbacks, concurrent workers,
cross-tenant identifiers, credential/log disclosure and unsafe deployment
composition. It does not create an observability platform or delivery pipeline.

## Closed HIGH findings

| Finding | Closure |
|---|---|
| SEC-021-H01 | A typed production profile and startup validator reject known/weak JWT keys, unsafe algorithms, missing dedicated keys, unsafe provider configuration, hosts and CORS. |
| SEC-021-H02 | The unsigned legacy WhatsApp router is not mounted in hardened production. The tenant-scoped signed raw-body flow remains canonical. |
| SEC-021-H03 | Anonymous `/messages` and `/conversation/message` routes are isolated in a legacy router and are not mounted in hardened production. |
| SEC-021-H04 | Login failures are normalized, unknown accounts execute a precomputed dummy Argon2 verification, passwords are bounded before hashing, and login uses rate limiting. |
| SEC-021-H05 | Public Organization bootstrap is not mounted in production; first-Owner creation locks Organization and is race-safe when explicitly enabled in development/test. |
| SEC-021-H06 | Current-user resolution rejects active tenant users whose Organization is inactive; Platform Admin global semantics remain available. |

## Production security profile

`BOTWA_ENVIRONMENT` is a closed `development`, `test`, or `production` profile
(`local` is accepted only as a compatibility alias for `development`). Production
fails startup unless all of these controls are explicit and safe:

- a strong JWT signing key and closed `HS256` algorithm;
- dedicated rate-limit, Audit cursor and OAuth state signing keys;
- a valid Fernet key for encrypted WhatsApp/Contact data and a Contact identity
  HMAC key;
- legacy core API, legacy WhatsApp and public bootstrap disabled;
- non-wildcard allowed hosts and safe CORS;
- no fake live provider;
- complete HTTPS callback/success URLs and secrets for providers that are enabled.

Providers that are not enabled do not require external credentials. Fernet
previous-key support remains the bounded rotation mechanism; KMS and a general
key-rotation framework are deployment follow-ups.

## Authentication and authorization

- JWT preserves `sub`, `auth_version` and `exp`; refresh tokens, MFA and a new
  session subsystem are out of scope.
- Missing user, wrong password, inactive user and inactive Organization share the
  same public `401 invalid credentials` login contract.
- Unknown users follow a precomputed dummy Argon2 path; no artificial sleep or
  per-request dummy hashing is used.
- Login/create/change password inputs have a 256-character maximum before Argon2.
- Existing access tokens fail closed for an inactive tenant Organization.
- Organization row locks serialize initial Owner creation and last-Owner
  demotion/deactivation. No owner-transfer subsystem was introduced.

## Multi-worker rate limiting

`security_rate_limit_bucket` stores only scope, HMAC key, UTC window, count,
optional block deadline and update timestamp. It never stores email, IP, token,
header or body plaintext. PostgreSQL `INSERT ... ON CONFLICT DO UPDATE RETURNING`
atomically increments a bucket across workers. Initial scopes are `auth_login`,
`public_bootstrap`, `whatsapp_webhook` and `billing_webhook`. Rejections return
`429`, a safe `RATE_LIMITED` code and `Retry-After`; they produce bounded security
logs but not an Audit row per hit. Forwarded addresses are honored only when the
visible peer is in the explicit trusted-proxy allowlist.

Every SQL consume also performs bounded opportunistic retention in the same
transaction. The default stale cutoff is 48 hours; the typed retention setting
is bounded from 24 hours plus one second to 30 days, always greater than the
maximum configurable 24-hour window, so current and potentially enforceable
buckets are never eligible. The cleanup selects the oldest rows through
`ix_security_rate_limit_bucket_updated_at`; its typed batch defaults to 200 and
is hard-bounded from 1 to 1,000. PostgreSQL uses `FOR UPDATE SKIP LOCKED`, while
SQLite retains a compatible bounded path.
Concurrent workers may claim disjoint cleanup batches safely. Repeated consumes
therefore progressively reclaim expired identity spray without an in-process
counter, background scheduler or PRD-023 job. Cleanup and atomic consume commit
together; any SQL failure rolls back and propagates instead of failing open.
Persistence remains HMAC-only.

Development/test may use the explicit in-process repository for isolation and
fast tests. Production composition always selects PostgreSQL persistence.

## Request and transport hardening

- An ASGI streaming limiter rejects oversized declared and chunked bodies before
  unbounded accumulation. Billing has a lower path-specific limit; signed
  WhatsApp continues to verify the unchanged raw bytes.
- `TrustedHostMiddleware` uses the configured allowlist. CORS is absent when no
  origins are configured and never permits wildcard plus credentials in
  production.
- API responses carry `X-Content-Type-Options: nosniff`, `Referrer-Policy:
  no-referrer` and `Cache-Control: no-store`. HSTS is emitted only for an explicit
  HTTPS production deployment.
- OpenAPI/docs are disabled by default and `/version` exposes only application and
  API version identifiers, not the deployment environment.
- OAuth `code`/`state` and existing sensitive query keys are redacted from access
  logs. Legacy provider failures no longer log or return raw provider bodies.

## Audit expansion

The existing PRD-017 append-only contract now covers successful security/admin
mutations for WhatsApp configuration, OAuth credential completion, Business
Configuration, Knowledge and Contacts. Events use allowlisted action/resource
types, resource UUIDs and typed/empty metadata only—never content, contact PII,
provider identifiers, ciphertext or secrets. The same SQLAlchemy Session and
transaction contain both mutation and Audit write; Audit persistence failure
rolls back the Unit of Work.

## Tenant and URL decisions

No new composite tenant foreign key was added: the reviewed PRD-021 paths already
load resources through tenant-scoped repositories, and no safe/data-loss-free
schema correction was demonstrated. Application invariants and tenant regression
tests remain authoritative; full PostgreSQL RLS is out of scope.
The Handoff cross-tenant regression is part of the approved security set, and
Platform Admin retains explicit organization scope when operating on tenant data.

No tenant-controlled outbound URL exists in the touched paths, so a speculative
SSRF framework was not added. Provider endpoints remain fixed, TLS verification
and timeouts remain enabled, and redirects remain disabled. A reusable URL policy
must precede any future tenant-configurable outbound URL.

## Container and dependency decisions

`.dockerignore` excludes `respaldos/`, `.env`, `.env.*`, `.git`, caches and local
build artifacts without inspecting `respaldos/`. The image runs as the dedicated
non-root `uid=10001(botwa)` user. No broader container/network production
hardening is claimed. The repository's current dependency constraints remain
unchanged; adopting a deterministic lock and automated vulnerability scan belongs
to PRD-023 because the current toolchain has no native lock workflow.

## Validation strategy

Focused tests cover startup rejection, JWT allowlisting, inactive Organization,
normalized authentication, dummy verification, password bounds, legacy shutdown,
429 semantics, HMAC-only buckets, streaming body limits, security headers,
OAuth redaction and sensitive Audit paths. Real PostgreSQL coverage validates the
`0021 → 0022 → 0021 → 0022` cycle, atomic multi-worker rate limiting, bounded
retention, expired identity-spray reclamation, active-bucket preservation, single
initial Owner and last-Owner protection. Existing webhook, Billing, Audit,
Handoff and tenant-isolation regressions preserve signed raw-body, dedupe,
provider binding and cross-tenant denial behavior.

Final approved validation:

| Gate | Result |
|---|---|
| Focused PRD-021 | 19 passed |
| Affected security regression | 129 passed |
| PostgreSQL PRD-021 | 6 passed |
| Migration cycle | `0021 → 0022 → 0021 → 0022` PASS |
| Ten-worker limiter | exactly 5/10 allowed; count 10; active bucket preserved; cleanup concurrency safe |
| Full pytest | 864 passed, 35 skipped, 2 warnings |
| mypy | PASS — 473 source files |
| Ruff | PASS |
| Black | PASS — 473 files |
| `git diff --check` | PASS |
| Alembic | `20260813_0022`, one head |
| Docker build/non-root | PASS |

## Deployment-only gates

These remain required before the corresponding production cutover but do not
reopen PRD-021 code closure:

- real Meta live smoke with approved credentials;
- real Mercado Pago sandbox plus commercial Billing configuration;
- DB least privilege and TLS verification;
- production reverse proxy/TLS and trusted-proxy configuration;
- provider credential provisioning;
- Platform Admin MFA decision;
- dependency lock/vulnerability scanning and release automation in PRD-023.

Real Meta validation remains blocked/pending approved external credentials; the
security hardening does not substitute the provider smoke. Billing commercial
enablement remains blocked by its existing Mercado Pago sandbox, provider and
commercial configuration gates; PRD-021 does not activate Billing.

## Non-goals

No WAF, SIEM, IDS, KMS migration, RLS, MFA implementation, refresh-session
subsystem, password reset, Observability platform, CI/CD pipeline,
dependency-lock workflow, pentest automation, Kubernetes or compliance program;
no security event ledger, automatic Audit retention/export or provider smoke
using unavailable credentials.

PRD-022 and PRD-023 remain **NOT STARTED**.
