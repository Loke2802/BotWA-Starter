# Response fidelity and recipient binding

This candidate integrates the conversation-quality and opt-in Ads-admission
changes locally. It does not activate Ads traffic, change quotas or runtime
configuration, or establish live model acceptance or WhatsApp delivery.

## Content review

Reviewer `luri-review-9` receives `segment_evidence`, resolved on the server from
the selected claim, its exact source facts and selected customer needs. This is
evidence, never approval. Unknown references fail before the call. The reviewer
still sees the full context, permissions, draft and cross-segment constraints.

The review asks whether each commercial assertion follows from its evidence,
including actor, object, scope, conditions and negations. It distinguishes
grammatical paraphrases from invented capabilities or outcomes. Describing a
customer's stated goal does not turn that goal into a provider promise. Prices,
protected clauses and unsupported bookings/payments remain constrained.

Real evaluation of reviewer 8 accepted five of six fictional full pipelines,
including the two-option tourism and architecture explanations, follow-up,
unconfirmed capabilities and a stop request. Two positive paragraph-only reviews
accepted the formerly rejected corporate-web paraphrase and an equivalent variant;
the neutral human-help offer passed and three unsupported action/capability
promises were rejected. These component checks do not replace full conversations.

The exact-price pipeline still failed with `STYLE_MISMATCH` on an honest price
uncertainty, while its scope question passed. The fallback then repeated an
unrequested service definition. The enum does not reveal the reviewer's precise
reasoning. Reviewer 9 aligns relevance with the current turn and the fallback
now handles a bounded price-only request without that definition. Deterministic
regression tests cover this correction; reviewer 9 has not yet had real-model
acceptance. No extra model stage or automatic retry is added.

## Recipient and line integrity

New jobs use a `routing-v1` digest in the existing `config_hash` column. It binds
configuration policy, organization, bot, conversation, WhatsApp configuration
and external phone-number ID, inbound
receipt, recipient and message sequence. Execution and dispatch compare that
snapshot and the receipt's tenant/line scope with the current conversation.

Before an AI retry, the processor also checks its job association, exact
idempotency key, receipt, line, encrypted recipient and recipient hash. A modified
idempotency prefix does not bypass the check: the job is found by outbound ID.
Reply context must match the source receipt when present. Approved conversational
text must still match its response checkpoint; existing memory/source fencing
remains required. Invalid encrypted payloads fail without calling the provider.

Immediately before sending, the outbox envelope must match tenant, bot, line,
recipient, text, reply context and notification kind. The sender independently
resolves the scoped active configuration and recipient permission. Existing
idempotency/unknown-delivery recovery rules remain in force; this does not promise
exactly-once delivery across a provider/network ambiguity.

Synthetic regression cases deliberately mutate these bindings and assert zero
provider calls. A valid retry targets the original recipient and line once.
They reveal missing integrity checks in the prior implementation, not evidence
that an actual customer received another customer's message.

## Scoped Ads transport

See [Ads-only admission](whatsapp-ads-only.md). The new server-side transport
exception requires scoped AI enabled, Ads-only enabled, a valid origin attached
to that exact tenant/bot/line conversation, an active webhook-enabled channel,
and the existing pilot-recipient policy. Installing the code leaves the feature
off. It never changes the global recipient restriction. Organic conversations
and unrelated tenants/lines do not gain permission.

## Upgrade compatibility and rollback

There is no migration. Old config-only job hashes intentionally fail closed under
the new reader; the old reader likewise cannot execute routing-v1 jobs. Do not
mix old/new admissions and consumers during rollout:

1. Pause new AI admissions using the existing scoped controls. Drain or cancel
   queued/running/ready jobs and pending recoverable attempts through canonical
   operations; verify counts. Do not delete history or silently replay old jobs.
2. Record the current immutable image/SHA, health, scoped flags and quota state.
   Deploy matching API and worker versions and verify both plus readiness.
3. Restore only the previously authorized pilot scope/recipient/quota, then run
   separately authorized controlled acceptance. Do not open customer traffic as
   a side effect of deployment.
4. Rollback pauses admissions and drains/cancels new-format jobs before restoring
   the previous image. Preserve data and the existing backup. The conversation
   schema compatibility rules in [commercial conversation](commercial-conversation.md)
   also apply.

## Required live acceptance before customer opening

- Within a separately approved spend limit, evaluate final full pipelines for
  useful service explanations, personalization, an unknown price, unsupported
  features, an appropriate human-help offer and stop/objection handling. Record
  actual wording, outcome/reason, calls, tokens and cost. Partial review approval
  is insufficient.
- In the controlled pilot, verify one actual incoming message, the generated
  response, exact target/line binding, provider acceptance, and the corresponding
  delivered/read status. `sent` means API acceptance, not handset delivery.
- Before Ads opening, test a real signed Click-to-WhatsApp referral and its
  follow-up, organic suppression, operator takeover and recovery. Agree the
  operating budget and explicitly authorize the customer scope.

Publication, merge, deployment, new real sends and model spending require the
owner's authorization. No live acceptance is claimed by this document.
