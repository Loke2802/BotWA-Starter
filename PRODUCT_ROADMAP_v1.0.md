# BotWA Product Roadmap v1.0

**Status:** PRD-006 Knowledge Management In Progress
**Date:** 2026-07-29

## Current State

Core v1.0.0 and Product v1.0.0 are released. Phase 3 Product Development has
completed PRD-001 through PRD-005. PRD-006 is implemented on its feature branch
and remains in progress pending CTO review and merge.

**MVP milestone:** PRD-001 through PRD-010.

## Phase 3 Sequence

| Order | Item | Status |
|---|---|---|
| 1 | PRD-001 Organizations | CLOSED |
| 2 | PRD-002 Authentication and Users | CLOSED |
| 3 | PRD-003 Roles and Permissions | CLOSED |
| 4 | PRD-004 Bot Management | CLOSED |
| 5 | PRD-005 Business Configuration | CLOSED |
| 6 | PRD-006 Knowledge Management | IN PROGRESS |
| 7 | PRD-007 WhatsApp Configuration | NOT STARTED |
| 8 | PRD-008 WhatsApp Live Messaging | NOT STARTED |
| 9 | PRD-009 Conversations Management | NOT STARTED |
| 10 | PRD-010 Human Handoff | NOT STARTED |
| 11 | PRD-011 Contacts and Customers | NOT STARTED |
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
| `pytest` | 557 passed, 1 warning |
| `ruff check app tests` | All checks passed |
| `black --check app tests` | 239 files would be left unchanged |
| `mypy app tests` | Success: no issues found in 239 source files |
| Docker/PostgreSQL | PASS - clean volume, migration, smoke, and restart persistence |

## PRD-006 Runtime Boundary

**BLOCKED RUNTIME INTEGRATION**

The conversation runtime currently does not resolve organization_id and bot_id.
The bot-scoped Knowledge provider is implemented and tested, but its runtime
connection to the Conversation Core is deferred to PRD-007 WhatsApp
Configuration, where bot-to-channel routing will establish that identity.

## Guardrails

- Product work must use existing Engines.
- Core architecture remains stable.
- New functionality must be tied to PRDs.
- Quality gates remain mandatory.
- Do not start PRD-007 without explicit CTO approval.
