"""Fail-closed structural controls; semantic review remains an additional defense."""

import hashlib
import re
import unicodedata

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
    if not required.issubset(inserted_clauses):
        raise ProviderError("MISSING_CANONICAL_CLAUSE")
    text = "\n\n".join(output)
    if not text.strip() or len(text) > min(3500, limit):
        raise ProviderError("RESPONSE_LENGTH")
    return text


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
