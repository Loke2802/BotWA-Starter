"""Bounded proposals; references are capabilities, never model-created facts."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from app.domain.generative_ai.contracts import StrictModel

Ref = Annotated[str, Field(min_length=1, max_length=100)]


class ResponseModel(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CustomerNeed(ResponseModel):
    id: str
    key: str
    value_ref: str
    evidence_ref: str
    status: Literal["evidence_backed"] = "evidence_backed"


class BusinessFact(ResponseModel):
    id: str
    subject: str
    predicate: str
    value_ref: str | None
    clause_ref: str | None = None
    source_ref: str
    source_version: str
    minimum: float | None = None
    maximum: float | None = None


class AuthorizedClaim(ResponseModel):
    id: str
    subject_refs: list[Ref] = Field(max_length=3)
    predicate: Literal[
        "attribute_equals",
        "need_matches_attribute",
        "source_clause",
        "same_published_attribute",
    ]
    fact_refs: list[Ref] = Field(max_length=10)
    need_refs: list[Ref] = Field(max_length=10)
    allowed_value_refs: list[Ref] = Field(max_length=10)
    required_clause_refs: list[Ref] = Field(max_length=3)
    expression_policy: Literal["paraphrase", "canonical_clause"]


class AllowedQuestion(ResponseModel):
    id: str
    need_key: str
    purpose: str


class ValidatedResponseContext(ResponseModel):
    schema_version: Literal["1"] = "1"
    context_id: Ref
    customer_needs: list[CustomerNeed] = Field(max_length=20)
    business_facts: list[BusinessFact] = Field(max_length=32)
    authorized_claims: list[AuthorizedClaim] = Field(max_length=62)
    validated_relationships: list[Ref] = Field(max_length=30)
    authorized_comparisons: list[Ref] = Field(max_length=10)
    uncertainties: dict[str, str]
    allowed_questions: list[AllowedQuestion] = Field(max_length=20)
    allowed_next_steps: dict[str, str]
    products: dict[str, str]
    canonical_values: dict[str, str]
    canonical_clauses: dict[str, str]
    style: Literal["luri-clear-warm-professional-v1"] = (
        "luri-clear-warm-professional-v1"
    )


class ResponseSegment(ResponseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    kind: Literal[
        "acknowledgement",
        "recommendation",
        "comparison",
        "question",
        "uncertainty",
        "next_step",
    ]
    text: str = Field(min_length=1, max_length=700)
    claim_refs: list[Ref] = Field(max_length=10)
    need_refs: list[Ref] = Field(max_length=20)
    question_ref: Ref | None
    next_step_ref: Ref | None
    uncertainty_ref: Ref | None


class ConversationalDraft(ResponseModel):
    schema_version: Literal["1"]
    context_id: Ref
    segments: list[ResponseSegment] = Field(min_length=1, max_length=8)


Reason = Literal[
    "OK",
    "UNSUPPORTED_CLAIM",
    "ALTERED_MEANING",
    "UNSUPPORTED_COMPARISON",
    "CUSTOMER_DATA_AS_BUSINESS_FACT",
    "REPEATED_QUESTION",
    "MULTIPLE_QUESTIONS",
    "UNAUTHORIZED_CONTACT",
    "ACTION_IMPLIED",
    "CLAUSE_CONTRADICTION",
    "INSTRUCTION_INJECTION",
    "STYLE_MISMATCH",
]


class SegmentReview(ResponseModel):
    segment_id: Ref
    approved: bool
    reason_code: Reason
    unsupported_claim_refs: list[Ref] = Field(max_length=10)


class SemanticReview(ResponseModel):
    schema_version: Literal["1"]
    context_id: Ref
    draft_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved: bool
    segments: list[SegmentReview] = Field(min_length=1, max_length=8)
