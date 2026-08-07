# BotWA Product Roadmap v1.0

**Status:** PRD-011 Contacts and Customers CLOSED (Contact only; Customer deferred)
**Date:** 2026-08-06

## Current State

Core v1.0.0 and Product v1.0.0 are released. Phase 3 Product Development has
completed PRD-001 through PRD-011. PRD-011 delivers Contact only; Customer is
deferred and CRM is not implemented.

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
| 12 | PRD-012 Automation Management | NOT STARTED |
| 13 | PRD-013 Integration Management | NOT STARTED |
| 14 | PRD-014 Dashboard | NOT STARTED |
| 15 | PRD-015 Analytics and Reports | NOT STARTED |
| 16 | PRD-016 Audit Log | NOT STARTED |
| 17 | PRD-017 Plans and Limits | NOT STARTED |
| 18 | PRD-018 Billing and Subscriptions | NOT STARTED |
| 19 | PRD-019 Onboarding | NOT STARTED |
| 20 | PRD-020 Security Hardening | NOT STARTED |
| 21 | PRD-021 Observability | NOT STARTED |
| 22 | PRD-022 CI/CD and Deployments | NOT STARTED |

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
| `pytest` | 645 passed, 1 warning |
| `ruff check app tests` | All checks passed |
| `black --check app tests` | 325 files would be left unchanged |
| `mypy app tests` | Success: no issues found in 325 source files |
| Docker/PostgreSQL | PASS - post-merge smoke, migration to `20260805_0013`, Contacts, Human Handoff, and restart |

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
- PRD-001 through PRD-011 are closed. PRD-011 implements Contact only; Customer
  is deferred, CRM is not implemented, and PRD-012 through PRD-022 are not started.
- PRD-010 documents lifecycle/RBAC, tenant isolation, suppression/resume,
  encrypted idempotent replies, archive protection, and migration chain
  `0010` → `0011` → `0012`.
