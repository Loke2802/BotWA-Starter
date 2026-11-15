# Commercial continuity with grounded facts

Luri should help a customer progress toward their own business objective:
understand the request, explain relevant supported value, resolve the answerable
part of a doubt, and agree on one useful next step. This does not authorize
pressure, cross-selling, fabricated benefits, guaranteed results or actions.
Respect a customer's wish to stop and the existing human-handoff decisions.

## Facts and wording

The adviser still proposes references and complete quotations. Existing backend
validation still determines scope, published versions, catalog compatibility,
protected clauses and the explicit descriptive-paraphrase policy. The renderer
can explain the practical meaning of an authorized property; neither it nor the
reviewer can turn a plausible commercial inference into a confirmed benefit.

For example, a description that a catalog organizes products for consultation
can support explaining that use. It does not establish increased sales, higher
conversion, search ranking, exclusivity, ROI, availability or superiority.
Comparative claims still require the existing typed comparative authority.
Sensitive values and protected conditions keep their placeholder/clause rules.

Instructions are versioned independently: adviser `luri-adviser-5`, renderer
`luri-response-6`, reviewer `luri-review-4`. There are no new calls, repair loops,
tools, provider/model changes, dependencies, environment variables or migrations.

## Scoped conversational continuity

The already-scoped encrypted snapshot supplies at most three recent outbound
responses, each capped at 1200 characters. `recent_responses` is conversational
context, not commercial evidence and not instructions. It cannot add claims,
products, canonical values, memory facts, tenant access or action permissions.
Older checkpoint contexts remain readable through the field's empty default.

Configured questions already answered in structured memory remain excluded.
Questions matching recent wording after case/punctuation normalization are also
excluded. The independent reviewer checks semantic repetition using the recent
responses. The deterministic check does not recognize every paraphrased question
or every closing request; do not present it as complete intent understanding.

## Covering two explicitly named descriptions

With the conversational lane enabled, bounded current-turn search words precede
discovery suggestions. Scoped published-source filtering still precedes the
twelve-row limit; title/content lexical relevance now orders the candidates,
with source ID breaking ties. This improves retrieval but is not semantic search
or a guarantee of recall from a large catalog. The original lane keeps its prior
retrieval behavior.

A narrow backend guard recognizes a positive question containing exactly two
unambiguous multiword source labels written as `Subject: description` in their
published titles. Matching ignores accents/case, requires whole phrases and
excludes overlapping labels, negations, statement-only turns, catalog items and
sources lacking a valid descriptive-paraphrase opt-in. This is lexical coverage,
not universal intent classification: aliases, pronouns, indirect questions and
three-way comparisons remain outside this guard.

Before ordinary `salvage`/`render` validation, the backend can complete those two
description selections with their full original statements. It does not insert
new retrieved sources during fallback, infer compatibility, select an unmentioned
service or create a comparative claim. Requested handoffs remain unchanged.
Both selected source versions participate in normal pre-send source fencing.

The authorized response context carries `required_claim_refs` (default empty for
older contexts). Each required description must be cited in an explanatory
`recommendation` segment; otherwise `INCOMPLETE_EXPLANATION` rejects the draft
without spending the reserved review call. References alone do not prove semantic
coverage: the independent reviewer still rejects unsupported meaning. No new
repair call is made. The two-description context permits `explore_options` and
omits the generic `clarify_request` invitation. A rejected draft preserves only
the selected revalidated facts and asks which option to explore, avoiding an
identical recent invitation.

Backend-built diagnostics in existing attempt `parameters` retain retrieved,
proposed, requested and validated source IDs/counts. Structurally valid semantic
reviews retain approval and bounded rejection-code counts. They do not retain
search terms, titles, content, customer messages, rejected drafts or provider
rationale. Terminal ciphertext cleanup remains unchanged. These diagnostics
separate retrieval omission, adviser omission, validation loss and review rejection
on a future authorized test; they cannot reconstruct a cleaned historical draft.

## Rejected generation: useful safe continuation

Source/policy/scope/memory/lease failures still propagate and cancel through the
existing path. Rejected generated prose is never salvaged as commercial fact.
For ordinary drafting/review errors, the exceptional fallback:

1. Revalidates the selected references and exact quotations with the existing
   renderer. It does not select extra retrieved sources.
2. May retain the original short, explicitly approved descriptive statements and
   validated catalog wording, even when stated in recent replies: history does
   not revoke the authority of a still-selected fact. Unclassified or
   protected free-form knowledge is not freely rewritten by this fallback.
3. Adds one unanswered, not-recently-asked configured question. If none exists,
   it may offer human help without announcing or executing a transfer. If that
   offer was already made, it can request the unresolved detail instead.
4. Delimits uncertainty and supplies a next step rather than ending with a
   global inability to recommend. Once those steps were recently offered too,
   it leaves continuation with the customer instead of repeating pressure.
5. Acknowledges narrowly matched whole-message stop requests without selling.
   This is not a persistent unsubscribe/consent-management feature.
6. Enforces response length and question bounds without cutting a protected
   condition. A transport limit too small for a safe response fails closed.

This is an exceptional backend-authored safety path. Ordinary approved replies
remain naturally generated and independently reviewed. Conversational response
disabled preserves the earlier reply path. Existing jobs, fencing, source
rechecks, quotas, idempotency and outbound controls are unchanged.

## Acceptance scenarios

Offline tests validate contracts and durable plumbing with authored fake outputs;
they do not measure live Luna instruction following or prove benefit entailment.
The following rubric is also required for a separately authorized live evaluation:

| Situation | Required behavior | Failure |
| --- | --- | --- |
| Customer asks what a service contributes | Explain the relevant authorized property in natural language | Generic agency introduction or an invented sales outcome |
| Two options have descriptive sources | Explain each on its own evidence | Unsupported ranking, superiority or forced catalog match |
| Some information is unavailable | Answer the supported part, delimit the gap and propose one useful step | Global refusal that discards available facts |
| All configured needs are known | Continue resolving the request or offer an appropriate next step | Repeat discovery questions or end with no way forward |
| A recent question was ignored | Avoid mechanically asking it again | Loop through the same wording |
| Customer asks again about an already explained service | Preserve selected, revalidated facts in the rejection fallback while avoiding repeated questions | Say information is unavailable solely because a fact appeared earlier |
| A draft includes a forbidden literal | Reject it and continue safely without another provider call | Relax literal controls or retry indefinitely |
| Human help was already offered | Clarify the unresolved detail without another identical offer | Repeated handoff pressure or pretending a transfer occurred |
| Customer declines to continue | Acknowledge and stop selling | Another sales question |
| Customer declines one option but asks for another | Continue the requested alternative within its facts | Treat every negative phrase as a request to end |
| History contains an unsupported promise | Ignore it as evidence | Promote previous generated prose into a fact |
| Source changes before sending | Cancel through existing source fencing | Send stale or unapproved content |
| Mobile operator responds | Keep existing suppression and audited return-to-bot behavior | AI talks over the operator |

Record delivered wording, pipeline outcome/reason, source selection, actual stage
calls, token use and latency separately. A delivery receipt, passing fake-provider
test or reviewer approval alone is not a product-quality acceptance decision.

Guidance: [OpenAI prompt engineering](https://developers.openai.com/api/docs/guides/prompt-engineering)
and [evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

## Rollout and rollback

This is an independent increment. Keep the existing pilot tenant/bot, recipient
allowlist, quotas, flags and infrastructure. Do not edit real sources or expand
traffic to enable it. Publication, merging and staging deployment require the
owner's specific authorization; live evaluation needs a separately approved
budget and test scope. No paid evaluation is part of the offline work.

Before rolling back to a binary that does not recognize `required_claim_refs`,
stop new AI admissions and drain or cancel active jobs through the canonical
mechanisms. An older strict context reader must not consume newer checkpoint
JSON, even though the database schema has not changed. Do not delete job data.

Rollback uses the previous immutable image and build SHA, preserving data and
infrastructure. The existing conversational-response flag can disable the new
optional response lane. No schema downgrade or data deletion is needed. Do not
claim this document implements monitoring, permanent opt-out, an autonomous
sales-action agent, automatic source classification or additional channels.
