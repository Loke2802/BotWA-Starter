# WhatsApp AI admission from ads

`generative_ai.whatsapp_ads_only` is a per-bot opt-in, default `false`. It is
independent of the conversation-quality candidate. Installing this code does not
enable customer traffic or change any existing bot setting.

When AI is enabled for the bot, this option admits only conversations with a
structured `referral` whose `source_type` is exactly `ad` and whose `source_id`
is a string of 1–64 ASCII digits. The existing webhook signature and line/tenant
resolution remain required. Customer message text, links, organic `post`
references, malformed referrals and delivery-status events never establish origin.
See [Meta's incoming webhook reference](https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/webhooks/whatsapp-incoming-webhook-payload).

The parser retains only the ad source ID, not ad copy, URLs, media or click IDs.
The existing encrypted receipt carries this field for crash recovery. AI ingress
records a minimal `whatsapp_ad_origin` in the existing conversation JSON, scoped
to its WhatsApp configuration. Follow-up messages do not need another referral.
This is conversation qualification, not a claim that every later message came
from an ad click. It remains until that conversation's origin is removed or the
conversation is replaced; no attribution expiry or conversion tracking is added.
While scoped AI is enabled, origin is recorded even if the pilot recipient list
blocks generation. Attribution is not backfilled from historical messages.

Unqualified messages still commit their receipts and encrypted history. They
enqueue no AI job and do not fall through to the legacy reply path while this
AI configuration is enabled. The gate is checked again during execution,
dispatch and transport retry. Config hashes retain their old value with the
option off; turning it on invalidates old queued policy snapshots. Recipient
allowlists, tenant scopes, quotas, channel availability, source validation and
human-handoff suppression remain additional requirements. Ad origin never
bypasses them or resumes a human-controlled conversation.

## Limits and rollout

- This covers supported text messages from Click-to-WhatsApp ads. Existing audio,
  image and other unsupported inbound handling remains unchanged.
- Ads leading to a website and then a normal WhatsApp link may not provide this
  referral. Missing evidence stays outside automatic attention; text matching is
  not a substitute. Confirm the actual campaign journey with a real webhook.
- No campaign-specific allowlist, public signup, advertising spend, automatic
  outbound campaign, prompt knowledge or ad-content ingestion is introduced.
- Do not remove the global outbound restriction for other bots just to admit
  these leads. Prepare a tenant-scoped transport policy before any wider rollout.
- Before activation: resolve the separate quality rejection, evaluate final
  conversations, agree the operating budget, verify real signed ad ingress,
  follow-up, organic suppression, operator takeover and recovery.
- No schema migration. For rollback, pause admissions and drain/cancel active
  jobs and recoverable receipts before an older reader: ad-bearing receipts have
  a new optional field and older strict readers do not support it. Remove the
  new config key through the audited configuration path before old code runs;
  do not delete receipts or conversation history.

Local synthetic tests exercise admission, continuity, isolation and policy
revocation without external model calls. They do not establish real ad delivery,
conversational quality, load capacity or readiness to open customers.
