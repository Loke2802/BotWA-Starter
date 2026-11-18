# Qualification for a business proposal

`generative_ai.qualify_for_proposal` is an optional, per-bot setting. It defaults
to `false`. It adds no environment variables, migrations, channel permissions or
changes to existing recipient, quota, routing and human-intervention guards.

With this setting enabled, the conversation collects configured needs for a
proposal rather than treating an unknown final price as a reason to stop.
Discovery owns customer intent. A transfer introduced only by the adviser (the
fact-selection stage) is ignored; a transfer identified by discovery is preserved.
The discovery instructions distinguish an explicit request for human attention
from a question about price or missing project details. This distinction still
needs live model evaluation; an authored-provider test does not establish model
accuracy.

The response context carries the setting and omits the generic `human_offer`
next step. Remaining configured questions respect evidence already in memory and
recently asked questions. The existing explicit-request and human-takeover flows
remain in place. A legitimate transfer still uses the existing handoff flow;
this change does **not** add a customer-facing handoff notification.

If the customer asks about price and configured questions remain unanswered, a
draft must ask one of those questions. A clear refusal of further questions is
excluded. A stalled draft falls back to the complete, revalidated literal price
clause (including its conditions) and one remaining configured question. Rejected
generated price prose is never reused, and a stale or changed source still fails
validation. Refusing further questions also suppresses fallback questions.

Reference prices, proposal format and package scope belong in the tenant's
published knowledge, not in provider instructions or application constants.
Monetary clauses retain their full canonical wording and conditions. A reference
for a basic package does not authorize attributing the generic product's entire
feature list to that package. Do not infer inclusions, deadlines or final prices.

Before enabling this mode for a tenant:

1. Inspect current published text and structured catalog attributes for outdated
   price claims. Prepare a scoped, audited update with original-value guards.
2. Reuse existing need keys so previously collected information remains useful.
   Add only missing questions, without resetting memory or handoff ownership.
3. Evaluate missing-price and reference-price conversations, repeated questions,
   explicit human requests, and unsupported scope claims with the real provider
   under a separately authorized budget.
4. Deploy matching API and worker code, then update configuration through the
   existing audited service while preserving quotas and recipient restrictions.
5. Verify the actual outbound attempt and provider delivery receipt in a
   separately authorized controlled test before opening customer traffic.
