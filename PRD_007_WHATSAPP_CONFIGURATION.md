# PRD-007 WhatsApp Configuration

**Status:** CLOSED - merged through PR #8
**Date:** 2026-07-30
**Product milestone:** MVP, increment 7 of 10

## Problem

BotWA needs tenant-safe administrative configuration for WhatsApp Cloud API
without making WhatsApp a dependency of the shared conversation platform.
Channel-specific identifiers and credentials must be protected, deterministic
channel routing must resolve product identity, and webhook requests must be
verifiable before PRD-008 introduces live messaging.

## Objectives

- Configure WhatsApp channels per organization and bot.
- Protect verify tokens, access tokens, and app secrets at rest.
- Resolve a phone number ID to a generic channel context using indexed SQL.
- Verify Meta webhook challenges and HMAC SHA-256 signatures.
- Pass resolved organization and bot identity to bot-scoped Knowledge.
- Establish an additive routing boundary reusable by future channel adapters.

## Scope

- Generic `ChannelIdentity`, `ResolvedChannelContext`, and `ChannelResolver`.
- `WhatsAppChannelConfiguration` contracts, service, repositories, ORM model,
  migration, dependencies, and administrative API.
- Draft, active, and inactive lifecycle.
- Environment-backed authenticated secret encryption and key rotation support.
- Secret rotation endpoint with safe configuration flags.
- WhatsApp channel resolver.
- Configuration-specific webhook verification and signature validation routes.
- RBAC, tenant isolation, SQL pagination/filtering, conflict handling, tests,
  Docker/PostgreSQL validation, and documentation.

## Out Of Scope

- Live inbound message processing or outbound calls to Meta.
- Changes to `ConversationMessage` or any Core Engine contract.
- Connection to `get_conversation_service()`.
- Message templates, media, retries, conversation management, or human handoff.
- Web chat, Telegram, Messenger, SMS, email, or speculative channel tables.
- PRD-008 WhatsApp Live Messaging.

## Actors And Permissions

| Role | Permissions |
|---|---|
| `viewer` | `whatsapp_config.read` |
| `operator` | Read, create configuration shells, and update non-sensitive fields |
| `organization_owner` | Full control |
| `organization_admin` | Full control |
| `platform_admin` | Full control through the existing cross-tenant mechanism |

Sensitive values supplied during creation additionally require
`whatsapp_config.rotate_secrets`. Activation requires
`whatsapp_config.activate`; secret rotation requires
`whatsapp_config.rotate_secrets`.

## Generic Channel Contracts

`ChannelIdentity` contains:

- `channel_type`;
- `external_channel_id`.

`ResolvedChannelContext` contains:

- `channel_type`;
- `organization_id`;
- `bot_id`;
- `channel_configuration_id`;
- `external_channel_id`.

`ChannelResolver` accepts an external channel identifier and returns a resolved
context. PRD-007 implements only `whatsapp`; future resolvers can implement the
same contract without changing a Core Engine.

## Data Model

`WhatsAppChannelConfiguration` contains:

- UUID primary key;
- organization and bot foreign keys;
- display name;
- globally unique `phone_number_id`;
- WhatsApp Business Account ID;
- globally unique opaque `public_webhook_id`;
- `draft`, `active`, or `inactive` status;
- webhook enabled flag;
- encrypted verify token, access token, and app secret fields;
- creator/updater foreign keys and timestamps.

Output DTOs never contain ciphertext or plaintext secrets. They expose only:

- `verify_token_configured`;
- `access_token_configured`;
- `app_secret_configured`.

## Administrative Endpoints

Base path:
`/organizations/{organization_id}/bots/{bot_id}/whatsapp-configurations`

| Method | Path suffix | Result |
|---|---|---|
| `POST` | `/` | Create draft, `201` |
| `GET` | `/` | SQL-filtered paginated list, `200` |
| `GET` | `/{configuration_id}` | Read safe DTO, `200` |
| `PATCH` | `/{configuration_id}` | Update non-sensitive fields, `200` |
| `DELETE` | `/{configuration_id}` | Delete, `204` |
| `POST` | `/{configuration_id}/activate` | Activate, `200` |
| `POST` | `/{configuration_id}/deactivate` | Deactivate, `200` |
| `POST` | `/{configuration_id}/rotate-secrets` | Rotate supplied secrets, `200` |

List filters are `status`, exact `phone_number_id`, display-name `search`,
`page`, and `page_size`. Pagination executes in SQL and page size is capped at
100.

## Lifecycle

Allowed transitions:

- `draft -> active`;
- `draft -> inactive`;
- `active -> inactive`;
- `inactive -> active`.

Activation requires an active organization, valid tenant bot, verify token, and
an app secret when webhook handling is enabled. Invalid or repeated transitions
return `409`. Mutations lock the target row with `SELECT ... FOR UPDATE`.

## Secret Handling

`SecretCipher` defines `encrypt` and `decrypt`.
`EnvironmentSecretCipher` uses Fernet authenticated encryption from
`BOTWA_WHATSAPP_SECRET_ENCRYPTION_KEY`.

- No encryption key is committed.
- Missing or invalid configuration returns controlled HTTP `503`.
- New encryption always uses the primary key.
- `BOTWA_WHATSAPP_SECRET_PREVIOUS_ENCRYPTION_KEYS` allows decryption during key
  rotation.
- DTOs, model representations, domain errors, and application logs do not expose
  secrets.
- The rotation operation encrypts only supplied values and commits once.

## Channel Routing

```text
phone_number_id
-> WhatsAppChannelResolver
-> ResolvedChannelContext
-> BotKnowledgeProvider(organization_id, bot_id)
```

Resolution uses a direct SQL query over the globally unique phone number ID and
accepts only active, webhook-enabled configurations. Draft, inactive, missing,
and ambiguous configurations do not resolve.

## Webhook Verification

`GET /webhooks/whatsapp/{public_webhook_id}` resolves an active configuration,
decrypts its verify token internally, compares it in constant time, and returns
the challenge only for `hub.mode=subscribe` and a matching token. All failures
return `403` without revealing the expected token.

## HMAC Signature Validation

`POST /webhooks/whatsapp/{public_webhook_id}/validate-signature` reads the raw
body and validates `X-Hub-Signature-256` in the form `sha256=<digest>` using the
decrypted app secret and constant-time comparison. It performs no live message
processing and makes no outbound call.

## Multi-Tenancy And Security

- Administrative queries always filter by organization and bot in SQL.
- The bot must belong to the organization in the route.
- Tenant users receive `403` before cross-tenant resource lookup.
- Platform admins use the existing scoped authorization path.
- Runtime lookup returns only the exact active configuration selected by a
  globally unique indexed identifier.
- Database uniqueness, `IntegrityError` rollback, generic domain conflicts, and
  `409` responses protect concurrent inserts.
- Lifecycle and rotation operations use row locking and one transaction.

## Knowledge Integration

The application integration test resolves an active phone number ID, obtains its
organization and bot, and queries `BotKnowledgeProvider` using that explicit
identity. Only published entries from that exact tenant and bot are returned;
draft, archived, other-bot, and other-tenant entries are excluded.

The Conversation Core is not wired in PRD-007. PRD-008 will consume the resolved
context when it implements live messaging.

## Migration

Migration `20260730_0008` follows `20260729_0007` and creates
`whatsapp_channel_configuration`, foreign keys, unique constraints, status
check, secret ciphertext fields, timestamps, tenant indexes, WABA index, and the
composite organization/bot/status index.

Required validation:

```text
alembic upgrade head
alembic downgrade 20260729_0007
alembic upgrade head
alembic heads
```

There must be one head: `20260730_0008`.

## Test Strategy

- Generic and WhatsApp domain contracts.
- Encryption, decryption, previous-key support, and safe representation.
- Lifecycle, RBAC, secret rotation, inactive users, and tenant isolation.
- In-memory and SQL repositories, filters, pagination, resolver, and conflicts.
- Webhook challenge and HMAC validation.
- Resolver-to-Knowledge integration.
- Migration metadata and clean PostgreSQL migration cycle.
- API restart persistence and full regression gates.
- Static regression preventing Core imports of WhatsApp product modules.

## Acceptance Criteria

- Configuration secrets are encrypted and never returned.
- Phone number and public webhook identifiers are globally unique.
- Draft and inactive configurations do not resolve.
- Active configurations resolve to the expected generic context.
- Correct challenge and signature pass; invalid input returns `403`.
- Tenant, RBAC, lifecycle, pagination, and conflict tests pass.
- Resolver-to-Knowledge identity and published-only behavior pass.
- Alembic has one head at `20260730_0008`.
- Pytest, Ruff, Black, mypy, Docker, PostgreSQL, and restart persistence pass.
- No Core Engine, public conversation contract, or live messaging behavior changes.

## Relationship With PRD-008

PRD-007 configures, protects, and resolves WhatsApp channels. PRD-008 consumes
this generic channel boundary for live-compatible inbound/outbound messaging.
The increments remain separate and PRD-007 owns no live transport behavior.

## Validation Results

| Gate | Result |
|---|---|
| `pytest` | PASS - 572 passed, 1 upstream warning |
| `ruff check app tests` | PASS - 0 errors |
| `black --check app tests` | PASS - 263 files unchanged |
| `mypy app tests` | PASS - 0 errors in 263 source files |
| Docker/PostgreSQL | PASS - API and PostgreSQL healthy |
| Alembic | PASS - upgrade/downgrade/upgrade, one head at `20260730_0008` |
| DB-backed persistence | PASS - encrypted configuration survives API restart |
| RBAC and multi-tenancy | PASS - viewer, operator, owner, platform admin, cross-tenant denial |
| Webhook security | PASS - challenge, HMAC, inactive blocking, access-log redaction |
| Resolver/Knowledge boundary | PASS - explicit organization and bot identity |

## Future Debt

- Validate with approved Meta credentials without changing stored-secret rules.
- Add future channel resolvers only under their approved PRDs.
