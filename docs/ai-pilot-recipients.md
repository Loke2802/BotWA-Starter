# Controlled AI recipients

An enabled bot can restrict generation with `settings.generative_ai.pilot_recipients`.
Values are international phone digits without `+`, spaces or punctuation, at most
20 unique entries. Configure this through the authenticated bot settings API,
preserving all existing settings and using the correct tenant/bot.

- `null` or an absent field preserves the existing unrestricted AI policy.
- `[]` blocks generation for everyone on this bot.
- A nonempty list permits only exact matching external sender identifiers.

This restriction supplements the global AI flag, tenant/bot pilot scope, bot
status, quotas and handoff. It grants no WhatsApp sending permission. Keep the
outbound recipient restriction enabled and configure its list separately.

For an excluded sender, the receipt and encrypted history still persist. No AI
job or legacy automatic reply is created by the conversation handler. Existing
independent automation rules retain their own behavior and must be reviewed
before enabling a real channel.

The worker checks recipients before generation and before dispatch. The transport
also rechecks AI policy before delivery/retry. Editing the list changes the job's
configuration hash, invalidating pending work under the previous configuration.
An omitted/null list preserves the historical hash. A provider call already in
flight cannot be undone, but policy is rechecked before further processing/send.

## Activation sequence

1. Verify staging identity, deployed commit, receipts/echoes, handoff and recovery.
2. Keep AI disabled while reviewing pending jobs/outbox and automation rules.
3. Set the selected bot's explicit pilot list and a conservative daily quota.
4. Configure its authorized Meta sending credential using the existing secret
   rotation service. Never place credentials or real phone numbers in Git.
5. Configure the same pilot scope in API and worker, preserve outbound restrictions,
   and verify the effective settings in both processes after deployment.
6. Enable only this bot and conversational response. Send a new message from the
   approved sender; do not replay previously stored messages as new input.
7. Verify durable job, usage, one response, delivery, mobile echo and handoff.

## Deactivation

Disable `generative_ai.enabled` on the selected bot first. An explicit empty pilot
list also revokes generation and invalidates pending work. Remove its global
pilot scope and sending credential if required, preserving receive-only history.
Verify no running/ready work can dispatch. Do not enable general recovery workers
or open the outbound allowlist as part of this operation.

No database migration, new infrastructure or additional environment variable is
required by this change. This document does not itself authorize activation.
