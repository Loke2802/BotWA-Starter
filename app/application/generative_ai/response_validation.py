"""Fail-closed structural controls; semantic review remains an additional defense."""

import hashlib
import re
import unicodedata

from app.application.generative_ai.response_continuation import (
    PRICE_REQUEST,
    declines_questions,
)
from app.domain.generative_ai.contracts import ProviderError
from app.domain.generative_ai.response_contracts import (
    ConversationalDraft,
    SemanticReview,
    ValidatedResponseContext,
)

TOKEN = re.compile(r"\{\{(product|value|clause):([a-z][a-z0-9_]{0,79})\}\}")
FORBIDDEN = re.compile(
    r"\d|https?://|www\.|@|%|[$€£]|\b(?:tel[eé]fono|whatsapp|descuento|gratis|reservado|enviado|pagado|garantizado)\b",
    re.I,
)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def normalize_conversation_references(
    context: ValidatedResponseContext, draft: ConversationalDraft
) -> ConversationalDraft:
    """Correct one unambiguous reference slot, never prose or authority."""
    if draft.context_id != context.context_id:
        return draft
    questions = {q.id for q in context.allowed_questions}
    segments = []
    changed = False
    for segment in draft.segments:
        ref = segment.question_ref
        if (
            segment.kind == "question"
            and ref is not None
            and ref in context.allowed_next_steps
            and ref not in questions
            and segment.next_step_ref is None
            and segment.uncertainty_ref is None
            and not segment.claim_refs
        ):
            segment = segment.model_copy(
                update={"kind": "next_step", "question_ref": None, "next_step_ref": ref}
            )
            changed = True
        segments.append(segment)
    return draft.model_copy(update={"segments": segments}) if changed else draft


def validate_draft(
    context: ValidatedResponseContext, draft: ConversationalDraft, limit: int
) -> str:
    if draft.context_id != context.context_id:
        raise ProviderError("CONTEXT_MISMATCH")
    claims = {c.id: c for c in context.authorized_claims}
    needs = {n.id: n for n in context.customer_needs}
    questions = {q.id for q in context.allowed_questions}
    ids: set[str] = set()
    seen_tokens: set[str] = set()
    question_count = 0
    output = []
    mentioned_claims: set[str] = set()
    inserted_clauses: set[str] = set()
    question_seen = False
    for segment in draft.segments:
        if segment.id in ids:
            raise ProviderError("DUPLICATE_SEGMENT")
        ids.add(segment.id)
        for refs, allowed in ((segment.claim_refs, claims), (segment.need_refs, needs)):
            if len(refs) != len(set(refs)) or any(ref not in allowed for ref in refs):
                raise ProviderError("INVALID_REFERENCE")
        if segment.question_ref and segment.question_ref not in questions:
            raise ProviderError("REPEATED_OR_UNKNOWN_QUESTION")
        if (
            segment.next_step_ref
            and segment.next_step_ref not in context.allowed_next_steps
        ):
            raise ProviderError("UNKNOWN_NEXT_STEP")
        if (
            segment.uncertainty_ref
            and segment.uncertainty_ref not in context.uncertainties
        ):
            raise ProviderError("UNKNOWN_UNCERTAINTY")
        if segment.kind == "uncertainty" and not segment.uncertainty_ref:
            raise ProviderError("MISSING_UNCERTAINTY")
        if segment.kind == "comparison" and not set(segment.claim_refs).intersection(
            context.authorized_comparisons
        ):
            raise ProviderError("UNSUPPORTED_COMPARISON")
        if segment.kind == "recommendation" and not segment.claim_refs:
            raise ProviderError("UNSUPPORTED_CLAIM")
        interrogative = bool(segment.question_ref or segment.next_step_ref)
        if question_seen and segment.kind in {
            "recommendation",
            "comparison",
            "uncertainty",
        }:
            raise ProviderError("PREMATURE_NEXT_STEP")
        question_seen = question_seen or interrogative
        if segment.kind in {"question", "next_step"} and not interrogative:
            raise ProviderError("UNAUTHORIZED_QUESTION")
        if ("?" in segment.text or "¿" in segment.text) and not interrogative:
            raise ProviderError("UNAUTHORIZED_QUESTION")
        if segment.text.count("?") > 1 or segment.text.count("¿") > 1:
            raise ProviderError("MULTIPLE_QUESTIONS")
        question_count += int(interrogative)
        if question_count > 1 or (segment.question_ref and segment.next_step_ref):
            raise ProviderError("MULTIPLE_QUESTIONS")
        literal = TOKEN.sub("", segment.text)
        if (
            "{" in literal
            or "}" in literal
            or FORBIDDEN.search(unicodedata.normalize("NFKC", literal))
        ):
            raise ProviderError("UNAUTHORIZED_LITERAL")
        if any(unicodedata.category(c) in {"Cc", "Cf"} and c != "\n" for c in literal):
            raise ProviderError("INVALID_FORMAT")
        allowed_values = {needs[n].value_ref for n in segment.need_refs}
        allowed_products: set[str] = set()
        allowed_clauses: set[str] = set()
        for ref in segment.claim_refs:
            claim = claims[ref]
            if claim.expression_policy != "canonical_clause":
                allowed_values.update(claim.allowed_value_refs)
            allowed_products.update(claim.subject_refs)
            allowed_clauses.update(claim.required_clause_refs)
        mentioned_claims.update(segment.claim_refs)

        def replace(
            match: re.Match[str],
            products: set[str] = allowed_products,
            values: set[str] = allowed_values,
            clauses: set[str] = allowed_clauses,
            template: str = segment.text,
        ) -> str:
            kind, ref = match.groups()
            token = match.group()
            if token in seen_tokens:
                raise ProviderError("DUPLICATE_PLACEHOLDER")
            seen_tokens.add(token)
            mapping, allowed = {
                "product": (context.products, products),
                "value": (context.canonical_values, values),
                "clause": (context.canonical_clauses, clauses),
            }[kind]
            if ref not in mapping or ref not in allowed or not mapping[ref]:
                raise ProviderError("INVALID_PLACEHOLDER")
            if kind == "clause":
                if template != token:
                    raise ProviderError("ALTERED_CANONICAL_CLAUSE")
                inserted_clauses.add(ref)
            value = mapping[ref]
            if "{{" in value or "}}" in value:
                raise ProviderError("INVALID_CANONICAL_VALUE")
            return value

        output.append(TOKEN.sub(replace, segment.text))
    required = {r for c in mentioned_claims for r in claims[c].required_clause_refs}
    explained = {
        ref
        for s in draft.segments
        if s.kind == "recommendation"
        for ref in s.claim_refs
    }
    if not set(context.required_claim_refs).issubset(explained):
        raise ProviderError("INCOMPLETE_EXPLANATION")
    if not required.issubset(inserted_clauses):
        raise ProviderError("MISSING_CANONICAL_CLAUSE")
    if context.required_question_ref and not any(
        segment.kind == "question"
        and segment.question_ref == context.required_question_ref
        for segment in draft.segments
    ):
        raise ProviderError("QUALIFICATION_QUESTION_MISSING")
    if (
        context.qualify_for_proposal
        and context.allowed_questions
        and context.customer_turn
        and PRICE_REQUEST.search(context.customer_turn.text)
        and not declines_questions(context.customer_turn.text)
        and not any(s.kind == "question" and s.question_ref for s in draft.segments)
    ):
        # A reference price is not the end of proposal qualification. Reject a
        # stalled draft and let the existing canonical continuation ask one
        # unanswered configured question. Never force it after a clear refusal.
        raise ProviderError("QUALIFICATION_QUESTION_MISSING")
    text = "\n\n".join(output)
    if not text.strip() or len(text) > min(3500, limit):
        raise ProviderError("RESPONSE_LENGTH")
    return text


def review_permissions(
    context: ValidatedResponseContext, draft: ConversationalDraft
) -> list[dict[str, str]]:
    """Server-resolved conversational authority, never a semantic approval."""
    permissions: list[dict[str, str]] = []
    questions = {q.id: q.purpose for q in context.allowed_questions}
    for segment in draft.segments:
        for kind, ref, allowed in (
            ("next_step", segment.next_step_ref, context.allowed_next_steps),
            ("question", segment.question_ref, questions),
            ("uncertainty", segment.uncertainty_ref, context.uncertainties),
        ):
            if ref is None:
                continue
            if ref not in allowed:
                raise ProviderError("INVALID_REFERENCE")
            permissions.append(
                {
                    "segment_id": segment.id,
                    "kind": kind,
                    "ref": ref,
                    "scope": allowed[ref],
                }
            )
    return permissions


def review_evidence(
    context: ValidatedResponseContext, draft: ConversationalDraft
) -> list[dict[str, object]]:
    """Project selected evidence, without deciding whether prose is faithful."""
    claims = {c.id: c for c in context.authorized_claims}
    facts = {f.id: f for f in context.business_facts}
    needs = {n.id: n for n in context.customer_needs}
    result: list[dict[str, object]] = []
    for segment in draft.segments:
        selected: list[dict[str, object]] = []
        for ref in segment.claim_refs:
            if ref not in claims:
                raise ProviderError("INVALID_REFERENCE")
            claim = claims[ref]
            if any(f not in facts for f in claim.fact_refs):
                raise ProviderError("INVALID_REFERENCE")
            selected.append(
                {
                    "claim": claim.model_dump(),
                    "facts": [facts[f].model_dump() for f in claim.fact_refs],
                }
            )
        if any(n not in needs for n in segment.need_refs):
            raise ProviderError("INVALID_REFERENCE")
        result.append(
            {
                "segment_id": segment.id,
                "commercial_evidence": selected,
                "customer_context": [needs[n].model_dump() for n in segment.need_refs],
            }
        )
    return result


def validate_review(
    context: ValidatedResponseContext,
    draft: ConversationalDraft,
    text: str,
    review: SemanticReview,
) -> None:
    expected = {s.id for s in draft.segments}
    actual = [s.segment_id for s in review.segments]
    if (
        review.context_id != context.context_id
        or review.draft_digest != digest(text)
        or len(actual) != len(set(actual))
        or set(actual) != expected
    ):
        raise ProviderError("INVALID_REVIEW")
    known = {c.id for c in context.authorized_claims}
    for result in review.segments:
        if any(ref not in known for ref in result.unsupported_claim_refs):
            raise ProviderError("INVALID_REVIEW")
        if result.approved != (result.reason_code == "OK") or (
            result.approved and result.unsupported_claim_refs
        ):
            raise ProviderError("INVALID_REVIEW")
    if review.approved != all(s.approved for s in review.segments):
        raise ProviderError("INVALID_REVIEW")
    if not review.approved:
        reason = next(s.reason_code for s in review.segments if not s.approved)
        raise ProviderError(f"REVIEW_{reason}")
