# BotWA Product Roadmap v1.0

**Status:** PRD-001 through PRD-015 CLOSED; PRD-016 IMPLEMENTED — PENDING CTO REVIEW
**Date:** 2026-08-08

## Current State

Core v1.0.0 and Product v1.0.0 are released. Phase 3 Product Development has
completed and closed PRD-001 through PRD-015. PRD-013 Integration Management is
closed after the final security merge via PR #20, PRD-015 Business Hours &
Holidays is closed after merge via PR #18, and PRD-014 Dashboard is closed after
merge via PR #22 at `04256eb0cb17e3d1fdb548edeae143578606d508` (final approved
head `8b836d7bb7b12fcf82ffb5bb8bbada4f3db758c6`). PRD-016 Analytics & Reports is
implemented pending CTO review; PRD-017 through PRD-023 are not started.

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
| 16 | PRD-016 Analytics and Reports | IMPLEMENTED — PENDING CTO REVIEW |
| 17 | PRD-017 Audit Log | NOT STARTED |
| 18 | PRD-018 Plans and Limits | NOT STARTED |
| 19 | PRD-019 Billing and Subscriptions | NOT STARTED |
| 20 | PRD-020 Onboarding | NOT STARTED |
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
| `pytest` | 721 passed, 15 skipped, 2 warnings |
| Focused PRD-016 plus Conversation/Handoff regression | 29 passed |
| PostgreSQL PRD-016 | 2 passed |
| PostgreSQL migration cycle | `0016 → 0017 → 0016 → 0017` PASS |
| `ruff check app tests` | All checks passed |
| `black --check app tests` | 400 files would be left unchanged |
| `mypy app tests` | Success: no issues found in 400 source files |
| `git diff --check` | PASS |
| Alembic | `20260808_0017 (head)` |

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
- PRD-001 through PRD-015 are closed. PRD-016 is implemented pending CTO review;
  PRD-017 through PRD-023 are not started.
- PRD-010 documents lifecycle/RBAC, tenant isolation, suppression/resume,
  encrypted idempotent replies, archive protection, and migration chain
  `0010` → `0011` → `0012`.
