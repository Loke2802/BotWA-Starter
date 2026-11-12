# Controlled knowledge paraphrasing

## Implemented scope

With conversational response enabled, an authorized knowledge editor can mark a
published **descriptive** entry as reference material rather than a literal
script. The backend still validates the adviser's complete quote against the
published source before building the response context. Only the selected,
validated description becomes a `source_statement` with `authorized_text` and a
`paraphrase` claim. Luna may express that meaning naturally or omit the claim if
it does not fit the current turn. It cannot turn customer assertions into facts.

The latest inbound message from the job's scoped snapshot is provided separately
as `customer_turn`, not as commercial authority. Needs remain evidence-backed;
their original values and the history are not rewritten by the rendering stage.

Every generated draft still passes structural validation and the independent
semantic review. A rejection cannot send the proposed paraphrase. When an
authorized unanswered need exists, fallback asks that question rather than
repeating a generic knowledge CTA. It otherwise retains the existing safe base.
No additional provider calls or retries are introduced.

## Permission and conservative boundaries

Default: unchanged literal clauses. No existing entry is automatically enabled.
No model output can opt a source in. Existing `knowledge.update` authorization,
tenant/bot checks and audit apply to the metadata change. The permission is bound
to SHA-256 of the exact full source content; a content edit invalidates it.
Changing policy through the knowledge service changes the source version; a
previously generated reply is cancelled at dispatch if its source changed.

Only descriptions up to 800 characters qualify. Catalog items always retain the
existing validation and immutable attribute clauses. A conservative lexical
guard refuses paraphrase for numbers (including normalized Unicode digits),
contacts, prices, availability, deadlines, ages, guarantees, negations,
conditions and other sensitive commercial expressions. These entries retain
their **whole original clause**; the backend never guesses how to split a
condition from its exception. Invalid, unknown or stale policy also stays literal.

The lexical guard is defense in depth, not proof of semantic fidelity or a
complete classifier for every language. The editor must review the source as a
description; the semantic reviewer remains mandatory. Do not mark arbitrary
commercial prose as descriptive. Fluent wording can still fail fidelity or
quality; real model evaluations are required before rollout.

## Prepare a source through the existing knowledge API

No migration, new secret, environment variable, infrastructure or dependency.
Use an authorized session in the existing API; never put session credentials in
documentation or chat. There is no new portal editor control in this increment.

1. GET the chosen entry under its exact organization and bot. Preserve its full
   current `metadata`, especially any unrelated fields. Confirm it is published,
   descriptive, at most 800 characters and contains no sensitive conditions.
2. Compute the content digest locally, preserving accents and punctuation:

   ```python
   from app.domain.generative_ai.knowledge_expression import content_digest
   print(content_digest("Creamos páginas para presentar los servicios de cada negocio."))
   ```

3. Merge this field into the metadata, replacing the placeholder with that digest:

   ```json
   {
     "response_expression": {
       "mode": "descriptive_paraphrase",
       "content_sha256": "<64 lowercase hex characters for the exact content>"
     }
   }
   ```

4. PATCH `/organizations/{organization_id}/bots/{bot_id}/knowledge/{entry_id}`
   with `{"metadata": <merged metadata>}` using the existing authenticated
   knowledge update endpoint. Verify its returned content, metadata, status and
   updated version. Do not edit or republish unrelated entries.
5. Keep the bot pilot scopes, recipient filters, quotas and outbound restrictions.
   Evaluate the first real output for relevance, grammar and fidelity as well as
   transport success. A synthetic provider test is not a model quality score.

This is the existing PATCH route in `app/api/knowledge_routes.py`; `entry_id`
corresponds to its `knowledge_id` path parameter.

## Rollback

Remove only `response_expression` from that entry's metadata through the same
scoped audited service, preserving other fields. New contexts use literal clauses;
queued replies tied to the older source version are cancelled. Existing history
and the original source content remain intact. Conversational response can also
be disabled through its existing bot flag. None of this disables an unrelated
tenant or changes the human takeover state.

## Verification and limitations

Synthetic tests cover opt-in, absent/malformed/stale policy, sensitive clauses,
catalog isolation, unselected sources, new-number/reference rejection, real
durable job → review → outbox flow with fake providers, reviewer rejection,
question fallback and policy revocation before dispatch. Provider calls are fake;
these are safety and plumbing checks, not evidence of actual Luna wording.

No live pilot source was edited or activated by this implementation. A generic
FAQ with conditions such as a promise about quotations remains literal; the
adviser should choose a pending question when the FAQ is unsuitable. Automatic
fact extraction from arbitrary prose, free rewriting of protected conditions,
a portal policy editor and a live quality score are not implemented.
