# Conversational quality: diagnosis and next contract

Status: local implementation of controlled descriptive paraphrasing, prompt
correction and acceptance plan. No deployment or paid evaluation is implied.
See [the implemented contract and activation procedure](knowledge-paraphrase.md).
The architecture below was preserved before implementation as a reference; the
implemented scope deliberately retains literal clauses for sensitive content.

## Observed failure

A controlled pilot completed discovery, adviser, conversational render and
semantic review. Its checkpoint was `approved`, not `fallback`. The selected
knowledge entry was a generic quotation request. It was copied completely, as
required by the current `source_clause` / `canonical_clause` contract. The result
repeated an already supplied objective and moved prematurely toward an adviser.
The acknowledgement also embedded a first-person customer fragment in a
second-person sentence. Fidelity checks passed; conversational quality did not.

The successful delivery and human takeover tests establish transport behavior,
not quality. Synthetic providers cannot establish real model quality either.

## Local correction

Adviser instructions now distinguish a relevant retrieved source from a suitable
answer, prefer a useful unanswered question, and omit unsuitable complete quotes.
Render instructions address grammatical perspective, expanded text and premature
sales endings. Review instructions explicitly use existing `STYLE_MISMATCH` and
`REPEATED_QUESTION` codes for those failures, including indirect questions in
canonical clauses. Stage prompt versions change for auditable attempts.

Tenant boundaries, quotas, model, routing and handoff remain unchanged. Published
descriptive sources can now explicitly authorize rewording, bound to their exact
content. All other sources retain canonical clauses. The latest scoped inbound
turn is supplied separately as untrusted conversational context. A rejected draft
uses an authorized unanswered question when available rather than pasting an
unsuitable FAQ. These controls do not constitute a live quality evaluation.

## Architectural reference: knowledge as facts, not a script

The owner wants authored texts to be reference material. Luna should choose and
compose a pertinent response from authorized meaning, rather than paste an FAQ.

The contract separates these capabilities explicitly:

* A backend-authorized, versioned factual projection for ordinary explanations,
  tied to the original tenant, bot and published source. The original text stays
  intact; an LLM-created summary cannot become a confirmed source.
* Explicitly protected values and clauses for prices, age ranges, availability,
  deadlines, commitments, policies, contacts and contractual conditions. Their
  existing preservation controls remain in force. Ambiguous free-form sources
  default to literal/abstain until classified; a prompt cannot classify them as
  safe or grant itself permission to paraphrase.
* Free natural wording supported by claim references to that factual projection.
  The independent semantic reviewer checks entailment, omissions, negation and
  conversational relevance. It must reject both invented facts and misleading
  simplifications; fluent prose alone never establishes truth.
* Conversation state that distinguishes the customer's current request, already
  answered needs, useful next question and a request for a person. It must be
  scoped, bounded and untrusted, and cannot act as commercial evidence.
* A safe, relevant fallback for quality rejection. Reverting blindly to a generic
  FAQ can reintroduce the same failure; rejection is not a successful answer.

Do not implement this by changing every `canonical_clause` to `paraphrase`, by
removing the reviewer or by allowing unvalidated retrieval documents into render.
Do not add infrastructure or an agent framework merely to obtain natural prose.

## Acceptance rubric

Evaluate actual outputs against these synthetic scenarios before enabling a new
version. These cases are planned, **not recorded as passed**. Use the authorized
pilot budget for any later real evaluation; do not automatically call a provider.

| Case | Context | Required behavior | Failure |
| --- | --- | --- | --- |
| Initial web request | Wants a website, show services and receive inquiries; business unknown | Recognize website context; ask the business activity once | Re-ask objective, generic quote CTA or unrelated services |
| Activity already given | Customer is a bakery | Continue from bakery and known website goal | Ask what the business does again |
| First-person need | Customer says “mostrar mis servicios” | Preserve customer perspective with natural wording or an explicit quotation | “Buscas mostrar mis servicios” |
| Direct price request | No authorized price | Explain limitation and ask one useful scoped question or offer a person | Invent a price, discount, or free service |
| Broad agency source | Many services exist but request is a website | Remain on website | Cross-sell other services without request |
| Unfit FAQ | Complete source asks for an objective already known | Omit it and ask a remaining useful question | Paste it because it is authorized |
| Deadline or condition | Source has a protected deadline and exception | Preserve both exactly under the fact contract | Drop exception or imply a guarantee |
| Explicit human request | Customer asks for a person | Use existing audited handoff | Continue interrogation or pretend a transfer occurred |
| Mobile human takeover | Business App reply then new inbound | Persist both; suppress AI until explicit return | AI answers over human |

Real quality acceptance includes grammar, relevance, factual support, one useful
next step and avoiding repeated questions. Record generation outcome separately
from semantic acceptance, final fallback and delivered text.

Reference: [OpenAI prompt engineering](https://developers.openai.com/api/docs/guides/prompt-engineering).
Representative evaluation cases are needed alongside instruction changes; a
passing deterministic test suite does not measure natural-language quality.
