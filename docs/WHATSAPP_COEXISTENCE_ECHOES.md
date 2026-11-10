# Business App coexistence echoes

## Scope

The signed, configuration-specific WhatsApp webhook accepts
`changes[].field=smb_message_echoes`, with `value.message_echoes[]` containing
`id`, `to`, `timestamp`, `type`, and optional `text.body`. It does not replay
history or app-state synchronization events as incoming client messages.

The resolved phone number must belong to the exact callback configuration,
organization and bot. A shared WABA does not grant access to another line.
No credentials, provider calls, additional infrastructure, migrations or new
environment variables are introduced by this increment.

## Durable behavior

- An echo is an observed human outbound message, not an inbound receipt or an
  outbound attempt. Text uses the existing encryption mechanism and is never
  logged. A deterministic primary key scoped to the line and provider event
  prevents duplicate history and counters across retries/restarts.
- PostgreSQL serializes echoes on the configuration row. Conversation identity
  uses the existing managed repository and line-aware fallback ID.
- The history row, counters, handoff and AI cancellation commit together.
  A transaction failure leaves the callback retryable, without partial success.
- A mobile intervention requests `waiting_human` with reason
  `business_app_reply`, without inventing an assigned portal user. An existing
  human assignment is preserved. Blocking automation does not depend on a
  commercial handoff entitlement: the human has already intervened.
- Pending/running/ready AI work is cancelled and unused reservations released.
  Pending AI delivery attempts and their history status become failed. Locked
  jobs/attempts are skipped to preserve the existing dispatch lock order; the
  durable handoff is rechecked by the existing generation and delivery gates.
- The operator claims the waiting thread in the portal and explicitly returns
  it to the bot when finished. Replaying a duplicate echo cannot undo that
  return. A new human message blocks it again.

## Boundaries

Media is represented as an intervention with content unavailable; this change
does not download or interpret attachments. Edit/revoke observations invalidate
the matching original outbound text for future model context while preserving
its encrypted history. This is not a complete edit-history synchronization UI.

A send already accepted by Meta or in flight before the intervention cannot be
recalled. A remote model call already in flight may finish and record its usage,
but its stale result cannot continue through the cancelled job. Echo delivery
latency and mobile/linked-device coverage must be tested on the actual
coexistence account; receiving an ordinary Cloud API test message is not proof.

## Validation and rollout

All automated provider calls use fakes. Unit tests cover duplicate/restart,
transaction rollback, first outbound message, media intervention, wrong phone,
another line of the same WABA, pending/running/ready jobs and queued delivery.
The canonical PostgreSQL suite additionally exercises duplicate concurrent
callbacks and AI interruption/outbox fencing on real row locks.

Before rollout: CI must pass, including PostgreSQL. Confirm the webhook schema
against the current official Meta reference and an actual signed coexistence
event. The official reference returned HTTP 429 during local preparation on
2026-11-09; external contract verification remains pending.

After an approved staging deployment, keep the recipient restriction in both
API and worker. Connect the real account through the supported owner-operated
coexistence onboarding, subscribe `smb_message_echoes` alongside `messages`,
and validate customer input, one bot reply, mobile human reply, one encrypted
history entry, blocked follow-up, portal claim and explicit return to the bot.
Do not migrate/delete the mobile number to bypass an unavailable onboarding flow.

Restoration of the encrypted backup, business content approval and the actual
human-handoff flow are separate pilot acceptance requirements. Opening the
recipient restriction is a separate owner-authorized action after these checks.

Rollback: close client traffic first using the existing channel/transport
controls. Restore the previous image only with traffic closed: it ignores mobile
echoes. Disabling AI alone is not a full shutdown because the legacy engine may
still answer. Existing history and waiting handoffs remain for an operator to
review; do not delete data to roll back.
