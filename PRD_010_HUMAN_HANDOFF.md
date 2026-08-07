# PRD-010 — Human Handoff

PRD-010 adds tenant-scoped human handoff to the WhatsApp channel runtime without
changing the Conversation Core. PRD-011 subsequently adds Contact linking without
placing Contact on Message or Handoff records.

## Lifecycle and authorization

`request` creates `waiting_human`; an eligible agent `claim`s it into
`human_active`; the assignee can `release`, `transfer`, `resolve`, or
`return-to-bot`. Owners/admins follow the existing privileged policy. Every
accepted transition records a `HandoffEvent`; tenant checks are applied before
resource access.

While a handoff is active, inbound customer messages remain in administrative
history while automatic Core replies are suppressed. Returning to the bot
re-enables the existing Core/outbound flow. Active handoffs block archive.

## Human replies and transport

The assigned agent sends a scoped reply that persists `author_user_id`,
encrypted text, and one linked `OutboundMessageAttempt`. Idempotency is unique
per organization. Timeout and 500 map to 503, 429 to 429, and invalid provider
requests to 400 without exposing provider payloads or sensitive values.

## Validation

Alembic chain: `20260730_0010` → `20260730_0011` → `20260730_0012`, one head.
PostgreSQL migration validation and an isolated Docker smoke covered signed
webhooks, lifecycle/RBAC, suppression/resume, encrypted persistence,
idempotency, cross-tenant denial, restart persistence, and cleanup. Real Meta
validation remains blocked by external credentials.
