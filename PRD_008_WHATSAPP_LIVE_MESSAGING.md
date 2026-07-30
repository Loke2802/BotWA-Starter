# PRD-008 WhatsApp Live Messaging

**Status:** IN PROGRESS - implementation and local validation complete, pending CTO review
**Date:** 2026-07-30
**Product milestone:** MVP, increment 8 of 10
**Depends on:** PRD-006 Knowledge Management and PRD-007 WhatsApp Configuration

## Problem

PRD-007 can configure, protect, and resolve a WhatsApp channel, but it does not
process inbound Meta events or deliver conversation responses. BotWA needs a
live-compatible transport that preserves the multichannel boundary, tenant
identity, security, idempotency, and recoverable delivery state.

## Objectives

- Receive signed WhatsApp Cloud API webhook POST events.
- Resolve `phone_number_id` into `ResolvedChannelContext`.
- Normalize supported inbound events into generic channel contracts.
- Execute the shared `ConversationService`.
- Query published bot knowledge using the resolved organization and bot.
- Deliver responses through an injectable Meta-compatible client.
- Prevent repeated webhook deliveries from duplicating Core execution or sends.
- Persist minimum inbound/outbound transport state without implementing PRD-009.
- Recognize provider delivery status events safely.

## Scope

- Inbound text messages end to end.
- Classification and controlled ignore for non-text message types.
- HMAC verification before payload parsing.
- Generic channel message contracts and handler/sender boundaries.
- Durable inbound receipts and encrypted outbound attempts.
- Deterministic long-text splitting.
- Initial delivery plus persisted bounded retry state.
- Fake and Meta-compatible clients.
- Provider status updates: sent, delivered, read, and failed.
- Structured metadata-only observability.

## Out Of Scope

- PRD-009 Conversations Management.
- PRD-010 Human Handoff.
- Administrative message inbox, search, filtering, or agent assignment.
- Media download or processing.
- Templates, campaigns, CRM, payments, analytics, or frontend.
- Web Chat, Telegram, Messenger, SMS, or email implementations.
- Distributed retry worker.
- Real Meta credential validation in automated or local smoke tests.

## Existing Component Audit

| Component | Decision | Reason |
|---|---|---|
| `ConversationService` | Reused unchanged | Shared deterministic conversation flow |
| `ConversationMessage` / `ChannelResponse` | Reused unchanged | Generic public contracts remain compatible |
| `get_conversation_service()` | Reused through dependency injection | Preserves established Core composition |
| `WhatsAppChannelResolver` | Reused | Provides deterministic tenant/bot identity |
| `ResolvedChannelContext` | Extended by use, not changed | Carries generic runtime identity |
| PRD-007 HMAC and `SecretCipher` | Reused | Validated security and key rotation boundary |
| `BotKnowledgeProvider` | Reused | Published-only knowledge with explicit tenant/bot |
| Structured logging | Reused | Safe event metadata without content |
| Integration Gateway | Not used in this path | Existing WhatsApp provider uses global credentials and returns provider bodies; PRD-008 requires per-channel encrypted credentials and stricter error contracts |
| Historical `WhatsAppAdapter`, `WhatsAppClient`, `WhatsAppSender` | Compatibility only | Existing unscoped `/webhooks/whatsapp` behavior remains available but is not used by the configured multi-tenant path |

PRD-008 adds no WhatsApp, Meta, WABA, or webhook DTO dependency to the
Conversation Core or other shared Engine flows. The historical WhatsApp provider
inside Integration Engine remains unchanged and is not used by this transport.

## Multichannel Architecture

```text
raw Meta webhook
-> signature validation
-> WhatsAppWebhookParser
-> WhatsAppInboundMessageMapper
-> WhatsAppChannelResolver
-> ResolvedChannelContext
-> ChannelConversationHandler
-> ConversationService
-> OutboundChannelMessage
-> WhatsAppChannelMessageSender
-> WhatsAppCloudApiClient
```

Future channels can implement their own parser, mapper, resolver, and sender
without modifying a Core Engine.

## Generic Contracts

### InboundChannelMessage

- `channel_type`
- `external_message_id`
- `external_sender_id`
- `external_recipient_id`
- `text`
- `timestamp`
- `resolved_context`
- limited scalar metadata

### OutboundChannelMessage

- `channel_type`
- `external_recipient_id`
- `text`
- optional `reply_to_external_message_id`
- limited scalar metadata

### Application Boundaries

- `ChannelMessageHandler`
- `ChannelMessageSender`
- `ChannelDeliveryResult`
- `MessageProcessingResult`

The Conversation Core receives only `ConversationMessage`; it never receives a
Meta payload or `phone_number_id`.

## Inbound Flow

`POST /webhooks/whatsapp/{public_webhook_id}`:

1. Enforces declared and actual body-size limits.
2. Reads raw bytes.
3. Validates `X-Hub-Signature-256` using the PRD-007 app secret.
4. Parses the payload only after HMAC succeeds.
5. Enforces an event-count limit.
6. Resolves each `phone_number_id`.
7. Confirms the resolved configuration matches the public webhook.
8. Maps text messages into `InboundChannelMessage`.
9. Creates or finds the durable receipt.
10. Acquires the receipt for processing.
11. Executes the shared conversation handler once.
12. Creates encrypted outbound attempt records.
13. Sends through the configured client.
14. Marks accurate receipt and attempt states.

## Supported Events

`text` is processed end to end.

The parser recognizes `image`, `audio`, `document`, `video`, `location`,
`contacts`, `interactive`, `button`, `reaction`, and `unknown`. These types are
ignored with HTTP 200 and structured metadata; no media is downloaded and no
receipt or outbound attempt is created.

Malformed individual events are skipped while valid sibling events can
continue. A globally malformed payload returns HTTP 400.

## Webhook Semantics

| Condition | HTTP result |
|---|---|
| Valid text or supported status payload | 200 |
| Duplicate receipt | 200 |
| Unsupported message type | 200 |
| Invalid or missing HMAC | 403 |
| Inactive, unknown, or mismatched channel | 403 |
| Globally invalid payload | 400 |
| Payload too large | 413 |
| Internal error after receipt creation | 200 after durable failed state |

The processor does not report a failed internal state as processed. It records
`failed` with a safe error code and acknowledges the webhook to avoid uncontrolled
provider retry storms.

## Conversation Core And Knowledge

`ChannelConversationHandler` creates a deterministic conversation UUID from:

- channel type;
- organization ID;
- bot ID;
- external sender ID.

It passes organization identity as `company_id`, channel type as `channel`, and
safe organization/bot/configuration metadata to the existing
`ConversationService`.

`BotKnowledgeProvider` is called with the resolved organization and bot. Only
published knowledge can be returned; draft, archived, other-bot, and
other-tenant entries remain excluded.

No Business Configuration runtime adapter was improvised. That integration
remains outside this transport increment unless approved separately.

## Meta Client

`WhatsAppCloudApiClient` defines `send_text_message`.

`MetaWhatsAppCloudApiClient`:

- validates API version and phone path identifiers;
- uses the configured Graph API version;
- decrypts the access token only immediately before sending;
- uses an explicit timeout;
- accepts an injected `httpx.AsyncClient`;
- normalizes the provider message ID;
- classifies timeout, network, 429, 5xx, auth, and request failures;
- never includes authorization, provider bodies, or message text in errors.

`BOTWA_WHATSAPP_LIVE_CLIENT_MODE` defaults to `disabled`. Production Meta access
requires explicit `meta`; local Docker smoke uses explicit `fake`.

## Fake Client

`FakeWhatsAppCloudApiClient` supports:

- success;
- timeout;
- HTTP 429;
- HTTP 400;
- HTTP 401;
- HTTP 500;
- deterministic provider message IDs;
- safe call counters and hashed identifiers.

It never records access-token values, full recipients, or text.

## Sender And Long Responses

`WhatsAppChannelMessageSender`:

- loads the exact organization/bot/configuration scope;
- requires an active, webhook-enabled channel;
- confirms the configuration phone ID matches the resolved context;
- decrypts the access token only in memory;
- validates recipient and text length;
- delegates delivery to the injected client.

Long messages are split deterministically on newline or whitespace where
possible, with a hard Unicode-safe code-point boundary fallback. Empty chunks
are not produced. Each chunk has an independent outbound attempt.

## Idempotency

`inbound_message_receipt` is a transport receipt, not conversation history.

Unique constraint:

```text
(channel_type, external_message_id)
```

States:

- received;
- processing;
- processed;
- failed.

The receipt stores tenant, bot, and channel configuration identity but not
message text. A processed, processing, or failed receipt is not automatically
re-executed by webhook redelivery.

PostgreSQL uniqueness plus row locking protects concurrent webhook copies. A
receipt found under different tenant identity is rejected.

## Outbound Persistence

`outbound_message_attempt` stores:

- optional inbound receipt;
- organization, bot, and channel configuration;
- hashed external recipient;
- encrypted recipient and response text for controlled retry;
- status and attempt count;
- provider message ID;
- safe error code;
- next retry time;
- provider status timestamp;
- created, updated, and sent timestamps.

It never stores an access token or plaintext payload.

## Retry Policy

Retryable:

- timeout;
- connection/network failure;
- HTTP 429;
- HTTP 5xx/provider unavailable.

Non-retryable:

- HTTP 400;
- HTTP 401/403;
- invalid recipient;
- missing token;
- inactive/missing configuration;
- invalid provider response.

The initial send increments the attempt count. Retryable failures remain
`pending` with deterministic exponential backoff capped by configuration.
`retry_attempt()` can execute a due attempt using encrypted persisted data.
There is no distributed scheduler in PRD-008; periodic execution is future debt.

## Delivery Status Events

The parser recognizes `sent`, `delivered`, `read`, `failed`, and unknown status.
Updates require the same resolved tenant/bot/configuration as the outbound
attempt. Unknown provider IDs are ignored.

Provider timestamps and status rank prevent regression from a newer state.
Repeated and out-of-order events are idempotent.

## Transaction Guarantees

- Receipt creation/acquisition is committed before Core execution.
- No receipt transaction remains open while the Core runs.
- Outbound attempt creation is committed before external delivery.
- Attempt count is committed before the HTTP call.
- Sent, pending-retry, and failed states are committed after delivery outcome.
- No database transaction is held during the Meta HTTP request.

The design targets at-most-once Core execution and prevents known duplicate
sends. It does not claim absolute exactly-once delivery: a network timeout can
occur after Meta accepted a message but before BotWA received its response.

## Security

- HMAC runs over raw bytes before JSON parsing.
- Constant-time digest comparison is inherited from PRD-007.
- Body size and event count are bounded.
- Access/app/verify secrets remain encrypted and outside DTOs.
- Recipient and response text are encrypted at rest.
- Logs exclude raw body, text, full phone/WA IDs, tokens, and signatures.
- Public runtime authorization is configuration HMAC, not user RBAC.
- No administrative message endpoint was added, so no new RBAC permission was
  introduced.

## Observability

Structured events:

- `whatsapp.webhook.received`
- `whatsapp.webhook.rejected`
- `whatsapp.message.duplicate`
- `whatsapp.message.processing_started`
- `whatsapp.message.processing_completed`
- `whatsapp.message.processing_failed`
- `whatsapp.outbound.started`
- `whatsapp.outbound.sent`
- `whatsapp.outbound.failed`
- `whatsapp.outbound.status_updated`

Allowed fields are correlation/receipt/tenant/bot/configuration IDs, message
type, status, duration, body size, and safe error code.

## Migration

Revision `20260730_0009` follows `20260730_0008` and creates:

- `inbound_message_receipt`;
- `outbound_message_attempt`;
- foreign keys and status checks;
- unique inbound channel/message identity;
- unique provider message ID;
- tenant, bot, configuration, status, created-time, and retry indexes.

Validated:

```text
alembic upgrade head
alembic downgrade 20260730_0008
alembic upgrade head
alembic heads
```

There is one head: `20260730_0009`.

## Acceptance Criteria

- A correctly signed text event resolves one active tenant/bot channel, executes
  the shared conversation flow, and records one outbound delivery attempt.
- Sequential, concurrent, and post-restart duplicates do not re-execute Core or
  create another outbound attempt.
- Unsupported events return a controlled acknowledgement without entering Core.
- Invalid signatures, unknown channels, malformed payloads, and oversized
  payloads follow the documented HTTP semantics.
- Published Knowledge is resolved only for the routed organization and bot.
- Outbound retries and delivery statuses persist without status regression.
- Sensitive configuration and message data do not appear in DTOs or logs and
  required retry data is encrypted at rest.
- Existing endpoints, Engines, PRD-001 through PRD-007, and the webhook challenge
  remain compatible.
- Alembic has one head and all quality gates are green.

## Test Strategy

- Unit tests cover generic contracts, mapper isolation, long-text splitting,
  fake/Meta client classification, sender scope, retry rules, and status ordering.
- Repository tests cover in-memory and SQL idempotency, locking-oriented
  acquisition, cross-tenant rejection, encryption, and persistence transitions.
- Endpoint tests cover HMAC-before-parse, malformed and oversized payloads,
  unknown routing, unsupported events, and controlled acknowledgements.
- Migration tests verify upgrade, downgrade, re-upgrade, constraints, indexes,
  and a single head.
- Full regression gates protect the five Engines and PRD-001 through PRD-007.
- Docker/PostgreSQL smoke validates the configured signed flow, concurrent
  deduplication, direct database evidence, delivery statuses, and restart
  persistence without contacting Meta.

## Validation Results

| Gate | Result |
|---|---|
| PRD-008 focused tests | PASS - 31 |
| `pytest` | PASS - 603 passed, 1 upstream warning |
| `ruff check app tests` | PASS - 0 errors |
| `black --check app tests` | PASS - 286 files unchanged |
| `mypy app tests` | PASS - 0 errors in 286 source files |
| Docker/PostgreSQL | PASS - clean volume |
| Alembic | PASS - upgrade/downgrade/upgrade, one `0009` head |
| Signed inbound text | PASS |
| Conversation Core and published Knowledge scope | PASS |
| Fake outbound and provider message ID | PASS |
| Sequential and concurrent deduplication | PASS |
| Delivery status ordering | PASS |
| Encryption and safe logs | PASS |
| API restart persistence | PASS |

## Real Meta Validation

**BLOCKED - EXTERNAL CREDENTIALS REQUIRED**

No automated test or Docker smoke contacted Meta. Real validation requires an
approved Meta app, channel credentials, externally reachable HTTPS webhook, and
explicit `BOTWA_WHATSAPP_LIVE_CLIENT_MODE=meta`.

## Relationship With PRD-009

PRD-008 stores only technical receipts and delivery attempts. PRD-009 now owns
administrative conversation history and lifecycle while preserving the transport
tables as the technical idempotency/delivery source of truth.

## Relationship With PRD-010

PRD-010 will own agent assignment and human handoff. PRD-008 does not add agent
state, queues, escalation UI, or handoff behavior.

## Non-Blocking Debt

- Run the same signed flow against an approved Meta sandbox/number.
- Add a scheduled worker for due outbound attempts.
- Define recovery policy for receipts left in `processing` after process crash.
- Decide whether historical unscoped WhatsApp endpoints should be deprecated in
  a separately approved compatibility change.
- Evaluate Integration Gateway adoption after it supports per-channel encrypted
  credentials and safe provider response handling.
