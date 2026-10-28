# Luri web chat: controlled pilot

Architecture reference, 28 October 2026. First site: kalivur.com. Delivery order
agreed with the owner: web chat, Instagram/Messenger, TikTok and LinkedIn subject
to official API access, corporate email, Telegram. This document does not imply
that those other connectors exist.

## Contract and boundaries

Reuse the site's floating widget and Luri's managed conversations, encrypted
messages, operator permissions, published knowledge and human handoff. Web is a
distinct channel; never impersonate WhatsApp identities, receipts or deliveries.
The initial web response is a verbatim published answer or an explicit fallback.
It makes no model calls, creates no AI jobs and executes no commercial actions.
The existing durable AI/evidence pipeline remains unchanged. Natural generative
web responses require a later delivery adapter and evaluation increment.

One server-configured organization/bot and explicit exact website origins form
the initial installation. Visitors cannot select a tenant or bot. A random,
expiring bearer capability grants access only to its own web conversation. Only
its digest, origin and expiry are persisted, separately from encrypted messages.
The browser keeps the capability in sessionStorage, never a URL or cookie.
Origin validation is an additional check, not authentication or bot protection.

Session creation, message submission, history polling, handoff and revocation
are separate bounded POST operations under /webchat. Each accepted visitor
message uses a client UUID idempotency key; conflicting reuse is rejected.
Conversation row locks serialize writes on PostgreSQL. Human replies reuse the
portal's assignment and authorization controls and are persisted for polling;
they never invoke a social provider. 'sent' means available in the web history,
not delivered/read by the visitor. Disabling the installation stops all public
reads and writes as well as new web operator replies.

No schema migration or new infrastructure is needed: the existing conversation
metadata and message tables support the contract. Rate limits use the existing
shared PostgreSQL security buckets in production, with bounded cleanup. Session
expiry revokes access; it does not erase the original transcript. Retention and
data deletion remain explicit owner-operated tasks, not an automatic recovery
worker. No new contact or marketing consent is inferred from anonymous chat.

## Release boundary

Keep the public widget disabled until the backend and full visitor/operator
round trip have passed in preview. kalivur.com is the intended first pilot, not
an instruction to point all public visitors to an unreviewed staging dataset.
Before publishing: choose the pilot environment, verify tenant and bot status,
published commercial facts, handoff entitlement/configuration, operator coverage,
privacy notice, TLS, exact origins and ingress protection. No paid AI or new
infrastructure is authorized by this increment.

## Acceptance checks

Verify unknown/wrong/expired tokens, wrong origin/tenant/bot, inactive scopes,
oversized bodies, rate limits, idempotent retries/conflicts, persisted restart
history, published-only knowledge, handoff suppression, operator permissions,
operator reply/polling and revocation. Verify WhatsApp still uses its original
transport and remains disabled. Frontend: TypeScript, ESLint, static build,
keyboard/mobile layout, failure handling and reload history.

## Configuration and operations

API environment (all are non-secret; use exact UUIDs from the portal):

```text
BOTWA_WEBCHAT_ENABLED=false
BOTWA_WEBCHAT_ORGANIZATION_ID=<organization UUID>
BOTWA_WEBCHAT_BOT_ID=<bot UUID>
BOTWA_WEBCHAT_ORIGINS=https://kalivur.com,https://www.kalivur.com
BOTWA_WEBCHAT_SESSION_TTL_SECONDS=86400
BOTWA_AI_ENABLED=false
```

The existing encryption key protects message contents; its existing rotation
rules also apply to web history. Production uses the existing rate-limit HMAC
key/PostgreSQL buckets. Never copy either key to the website or chat. Public
sessions last at most 24 hours and contain at most 200 messages. Default limits
per peer per minute: 6 session creations, 12 writes/handoffs, 60 history reads;
installation-wide minute ceilings are ten times these values. Use the documented
trusted proxy configuration; do not trust arbitrary X-Forwarded-For headers.
Session creation and new messages require the existing knowledge plan feature.
Anonymous handoff additionally requires the bot's handoff setting and plan.

Website build:

```text
NEXT_PUBLIC_LURI_CHAT_ENABLED=false
NEXT_PUBLIC_LURI_CHAT_URL=https://<approved-pilot-api>/webchat
```

These are build-time values. Enabling requires an explicit true and a rebuild;
merely retaining an old CHAT_URL cannot activate the widget. Use localhost
origins and URLs only for local tests. The static site has no server/API route.
Do not install the historical standalone botwa_webchat.py prototype.

Public API: POST /webchat/sessions accepts {}; returns token and expires_at.
POST /webchat/messages accepts message and UUID idempotency_key. POST history,
handoff and close accept {}. All four require Authorization: Bearer <session>
and the exact creation Origin. Never put this token in logs, URLs or screenshots.
The visitor UUID is not a phone, email, confirmed lead or marketing consent.

Operator procedure: portal → Conversaciones → Visitante web → Tomar atención →
Respuesta humana → Enviar respuesta. Existing tenant, assignment and permission
checks still apply. The visitor sees the answer on the next visible-panel poll
(normally 10 seconds). Hidden tabs do not poll. Resolved handoffs require a new
visitor session; returning to Luri explicitly re-enables published answers.
Finalizar conversación revokes the visitor capability, preserves the transcript
and does not silently resolve an assigned operator's work.

Rollback: set BOTWA_WEBCHAT_ENABLED=false and restart/redeploy the API; set the
website flag false and rebuild/publish using the existing Sites procedure. This
does not change WhatsApp or AI flags and requires no database downgrade. With
the API flag off, new web operator replies also fail closed. Historical messages
remain readable to authorized portal users. Expiry is access revocation, not
automatic deletion; document the pilot retention period and owner-operated
deletion process before opening public traffic. Never claim automatic retention
or account verification is implemented by this increment.

Still outside scope: real generative web responses/AI job delivery; multi-site
embed loader and self-service installation management; contact capture/identity
verification; social connectors; a new worker; a public production rollout.
