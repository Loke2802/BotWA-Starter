# BotWA Product Roadmap v1.0

**Status:** PRD-001 through PRD-019 CLOSED; PRD-020 IMPLEMENTED — PENDING CTO REVIEW; PRD-021 through PRD-023 NOT STARTED
**Date:** 2026-08-13

## Current State

Core v1.0.0 and Product v1.0.0 are released. Phase 3 Product Development has
completed and closed PRD-001 through PRD-015. PRD-013 Integration Management is
closed after the final security merge via PR #20, PRD-015 Business Hours &
Holidays is closed after merge via PR #18, and PRD-014 Dashboard is closed after
merge via PR #22 at `04256eb0cb17e3d1fdb548edeae143578606d508` (final approved
head `8b836d7bb7b12fcf82ffb5bb8bbada4f3db758c6`). PRD-016 Analytics & Reports is
closed after PR #24 at merge commit
`601499071f39aad85dc4d9595fc04425f40a3962`, with final approved head
`6cafee11a0f807e07a9277eae98e128ab68aa711`. PRD-017 Audit Log is closed after
PR #26 at merge commit `01c809c909360f4a31a6b26b1d4126a1c98e9c8b`, with final
approved head `3f7808da24d0dc1e3b5d6f3d337ee4562f5398b6`. PRD-018 Plans and Limits is
closed after PR #28 at merge commit
`63f2fc79444e6b3f85b516b917860fb17fa8f779`, with final approved head
`2776a1b2ca6082142f14862c4eac4cf889eea631`. PRD-019 Billing & Subscriptions is
closed after normal merge PR #30 at
`5a87ffc32be4315ebb6f9e64826bdb96f36ada58`, with final approved implementation
head `2a15b7f022c2989d73bb97d9b964495dba961778`. Billing remains disabled by
default and commercial enablement remains blocked by configuration and real
Mercado Pago sandbox gates. PRD-020 Onboarding is implemented pending CTO review
as a minimal historical workflow with derived current readiness and revision
`20260813_0021`. PRD-021 through PRD-023 are not started.

**MVP milestone:** PRD-001 through PRD-010.

## Phase 3 Sequence

| Order | Item | Status |
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
| 16 | PRD-016 Analytics and Reports | CLOSED |
| 17 | PRD-017 Audit Log | CLOSED |
| 18 | PRD-018 Plans and Limits | CLOSED |
| 19 | PRD-019 Billing and Subscriptions | CLOSED |
| 20 | PRD-020 Onboarding | IMPLEMENTED — PENDING CTO REVIEW |
| 21 | PRD-021 Security Hardening | NOT STARTED |
| 22 | PRD-022 Observability | NOT STARTED |
| 23 | PRD-023 CI/CD and Deployments | NOT STARTED |

## Release History

| Milestone | Status |
|---|---|
| Core v1.0.0 | RELEASED |
| Product v1.0.0 | RELEASED |
| Release Candidate Review after PRD-005 | CLOSED |
| WhatsApp real/live validation with approved credentials | BLOCKED - EXTERNAL CREDENTIALS REQUIRED |

## Latest Validated Gates

| Gate | Result |
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

## Channel Runtime Boundary

**IDENTITY ROUTING AND LIVE-COMPATIBLE TRANSPORT IMPLEMENTED**

PRD-007 resolves a WhatsApp `phone_number_id` to a generic
`ResolvedChannelContext` containing organization and bot identity. That identity
is consumed by PRD-008 through generic inbound/outbound channel contracts,
bot-scoped Knowledge lookup, the unchanged Conversation Core, durable
idempotency, encrypted delivery attempts, and an injectable Meta-compatible
client. Real Meta validation remains blocked by external credentials.

## Conversation Management Boundary

PRD-009 extends the existing Core conversation/message persistence with scoped
administrative lifecycle, encrypted channel history, SQL pagination, and separate
content-read authorization. Receipts and outbound attempts retain their PRD-008
technical responsibilities. PRD-010 Human Handoff is closed following merge and
post-merge validation.

## Guardrails

- Product work must use existing Engines.
- Core architecture remains stable.
- New functionality must be tied to PRDs.
- Quality gates remain mandatory.
- PRD-001 through PRD-019 are closed. PRD-020 is implemented pending CTO review.
  PRD-021 through PRD-023 are not started.
- PRD-010 documents lifecycle/RBAC, tenant isolation, suppression/resume,
  encrypted idempotent replies, archive protection, and migration chain
  `0010` → `0011` → `0012`.
