# PRD-009 Conversations Management

**Status:** CLOSED - integrated with PRD-010 and PRD-011 Contact linking
**Date:** 2026-07-30
**Product milestone:** MVP, increment 9 of 10
**Depends on:** PRD-001 through PRD-008

## Problem And Objectives

The Conversation Core already persists operational state and basic messages, while
PRD-008 persists transport receipts and delivery attempts. Neither is an
administrative, tenant-scoped conversation history. PRD-009 extends the existing
`conversation` and `message` tables so authorized users can safely list logical
conversations, inspect encrypted content, and manage their lifecycle.

It must preserve the Core and transport boundaries, avoid duplicate history for
webhook retries, and maintain strict organization/bot isolation.

## Scope

- Tenant and bot scoped logical conversations for generic channels.
- Deterministic identity: organization, bot, channel, and external customer.
- Encrypted inbound/outbound administrative message records.
- Paginated conversation and message APIs.
- `open`, `closed`, and `archived` lifecycle.
- Separate RBAC permissions for metadata and full content.
- Optional links to PRD-008 receipts and outbound attempts.

## Out Of Scope

- Human assignment, takeover, queues, agent replies, inbox UI, notes, tags,
  contacts CRM, analytics, exports, WebSocket, or any PRD-010 capability.

## Actors And Permissions

| Actor | Access |
|---|---|
| viewer | `conversation.read` metadata only |
| operator | metadata, content, close/reopen |
| organization owner/admin | metadata, content, close/reopen, archive |
| platform admin | existing controlled cross-tenant access |

`conversation.read_content` is intentionally separate from `conversation.read`.

## Existing Component Audit

| Component | Decision |
|---|---|
| `ConversationModel` / `MessageModel` | Extended; no parallel source of truth |
| `ConversationService` / state manager | Reused unchanged in responsibility; optional persistence flag avoids duplicate message rows in managed channel flow |
| `ChannelConversationHandler` | Reused with a managed application wrapper |
| `InboundMessageReceipt` | Remains transport idempotency only |
| `OutboundMessageAttempt` | Remains provider delivery/retry source of truth |
| `SecretCipher` | Reused for message content at rest |

The legacy Core state stored in `conversation.status` remains distinct from the
administrative lifecycle stored in `management_status`.

## Data Model And Identity

`conversation` gains nullable tenant-management columns for compatibility with
legacy Core rows. New PRD-009 rows always populate organization, bot, channel,
external customer, lifecycle, activity timestamps, and counters. A partial unique
identity index protects `(organization_id, bot_id, channel, external_customer_id)`
for managed records.

`message` is extended rather than replaced. Managed records keep `content` empty,
place plaintext only in `text_ciphertext`, and store direction, channel, event
identifiers, delivery status, safe metadata, occurrence time, and optional receipt
or attempt references.

## Lifecycle

Administrative transitions are `open -> closed`, `closed -> open`, and either
open/closed to `archived`. An inbound message reopens a closed conversation. An
archived conversation is never silently reopened; its inbound processing is
recorded as a controlled failure.

## Channel And Core Integration

```text
receipt acquired
-> managed handler resolves or creates conversation
-> encrypted inbound message recorded once
-> unchanged Conversation Core executes
-> inbound marked processed
-> encrypted outbound message created per outbound attempt
-> sender delivers
-> attempt status synchronizes to administrative message
```

No database transaction remains open over the external provider HTTP request.
This provides at-most-once administrative record creation for known receipt/attempt
identities; it does not claim absolute exactly-once delivery under ambiguous network
failure.

## Search, Filters, And Pagination

Listings are SQL-scoped by organization and optionally filter bot, channel,
lifecycle, exact external customer identity, and inbound/outbound presence. The
returned shape is `items`, `total`, `page`, `page_size`, `has_next`, and
`has_previous`. Messages are ordered by `occurred_at, id`; full histories are never
embedded in a conversation list. There is no decrypt-in-memory full-text search.

## Security, Privacy, And Observability

- Message text uses existing authenticated encryption at rest.
- Lists expose a masked customer identifier, not the complete external identity.
- Full message text requires `conversation.read_content`.
- No secret, raw webhook body, plaintext message, ciphertext, or full external ID
  is placed in logs.
- Structured events cover conversation list/detail access and lifecycle changes.
- Retention, deletion policy, and preview search remain future work.

## Migration

Revision `20260730_0010` follows `20260730_0009` and extends the existing tables
with tenant-scoped indexes, lifecycle checks, message direction/status checks,
optional transport links, and partial uniqueness for managed identities/messages.
Legacy rows are preserved because the new management columns are nullable.

## Acceptance Criteria

- A signed PRD-008 inbound creates one managed conversation and one encrypted
  inbound history record.
- Each outbound attempt creates at most one encrypted outbound history record.
- Duplicate receipts do not duplicate conversations or message history.
- Provider status updates synchronize the linked outbound history status.
- SQL listing, detail, and history are scoped and paginated.
- Reader and content-reader permissions remain distinct.
- Closed conversations reopen only through the documented policy; archived rows do
  not silently reopen.
- PRD-010 remains unimplemented.

## Test Strategy And Future Debt

Unit and repository tests cover identity, deduplication, encryption, lifecycle,
status synchronization, counters, pagination, and tenant isolation. API/RBAC,
migration, PRD-008 integration, Docker/PostgreSQL restart, and controlled logging
are validated before review.

Validated results: `606 passed, 1 warning`; `ruff check app tests` clean;
`black --check app tests` leaves 297 files unchanged; and `mypy app tests`
reports no issues in 297 source files. Docker/PostgreSQL validation applied
`20260730_0010`, exercised a signed inbound flow, lifecycle and RBAC, API restart,
and downgrade/upgrade back to the single head.

Non-blocking debt: retention policy, safe preview/full-text search, and repair
of legacy unscoped Core rows. PRD-010 now integrates through the managed
conversation boundary: active handoffs prevent archive and suppress automatic
Core delivery while retaining inbound administrative history.
