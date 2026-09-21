"""Projection built only after PR44 validation, with no raw retrieval documents."""

from typing import Any

from app.application.generative_ai.validation import render
from app.domain.generative_ai.contracts import AdviserResult, AIConfig, CatalogItem
from app.domain.generative_ai.response_contracts import (
    AllowedQuestion,
    AuthorizedClaim,
    BusinessFact,
    CustomerNeed,
    ValidatedResponseContext,
)


def build_context(
    context_id: str,
    result: AdviserResult,
    config: AIConfig,
    memory: dict[str, Any],
    sources: dict[str, dict[str, Any]],
) -> ValidatedResponseContext:
    # The projection cannot be used as a bypass around the existing validators.
    render(result, config, memory, sources)
    values: dict[str, str] = {}
    needs = []
    for key, value in memory.items():
        ref = f"need_{key}"
        values[ref] = value["value"]
        needs.append(
            CustomerNeed(
                id=ref, key=key, value_ref=ref, evidence_ref=value["message_ref"]
            )
        )
    products: dict[str, str] = {}
    clauses: dict[str, str] = {}
    facts = []
    claims = []
    relationships = []
    comparisons: list[str] = []
    comparable: dict[str, tuple[str, str, float | None, float | None]] = {}
    for index, recommendation in enumerate(result.recommendations):
        product = f"product_{index}"
        source = sources[recommendation.item_ref]
        item = CatalogItem.model_validate(source["catalog"])
        products[product] = item.name
        for match in recommendation.matches:
            attribute = next(a for a in item.attributes if a.key == match.attribute_key)
            fact = f"{product}_{attribute.key}"
            if fact in values:
                continue
            values[fact] = attribute.value
            comparable[fact] = (
                attribute.key,
                attribute.value,
                attribute.minimum,
                attribute.maximum,
            )
            facts.append(
                BusinessFact(
                    id=fact,
                    subject=product,
                    predicate=f"attribute:{attribute.key}",
                    value_ref=fact,
                    source_ref=recommendation.item_ref,
                    source_version=source["version"],
                    minimum=attribute.minimum,
                    maximum=attribute.maximum,
                )
            )
            # Generic catalog attributes do not have a reliable sensitivity type.
            # Preserve their complete authorized wording rather than guessing
            # whether a label describes a warranty, safety or availability claim.
            clauses[fact] = f"{item.name} — {attribute.label}: {attribute.value}"
            claim = f"claim_{fact}"
            claims.append(
                AuthorizedClaim(
                    id=claim,
                    subject_refs=[product],
                    predicate="need_matches_attribute",
                    fact_refs=[fact],
                    need_refs=[f"need_{match.need_key}"],
                    allowed_value_refs=[fact],
                    required_clause_refs=[fact],
                    expression_policy="canonical_clause",
                )
            )
            relationships.append(claim)
    product_facts = list(facts)
    for index, left in enumerate(product_facts):
        for right in product_facts[index + 1 :]:
            if (
                left.subject == right.subject
                or comparable[left.id] != comparable[right.id]
            ):
                continue
            ref = f"compare_{len(comparisons)}"
            if len(comparisons) >= 10:
                break
            comparisons.append(ref)
            claims.append(
                AuthorizedClaim(
                    id=ref,
                    subject_refs=[left.subject, right.subject],
                    predicate="same_published_attribute",
                    fact_refs=[left.id, right.id],
                    need_refs=[],
                    allowed_value_refs=[left.id, right.id],
                    required_clause_refs=[left.id, right.id],
                    expression_policy="paraphrase",
                )
            )
    for index, quote in enumerate(result.knowledge):
        ref = f"knowledge_{index}"
        source = sources[quote.source_ref]
        clauses[ref] = quote.quote
        facts.append(
            BusinessFact(
                id=ref,
                subject=ref,
                predicate="source_clause",
                value_ref=ref,
                source_ref=quote.source_ref,
                source_version=source["version"],
            )
        )
        claims.append(
            AuthorizedClaim(
                id=f"claim_{ref}",
                subject_refs=[],
                predicate="source_clause",
                fact_refs=[ref],
                need_refs=[],
                allowed_value_refs=[],
                required_clause_refs=[ref],
                expression_policy="canonical_clause",
            )
        )
    next_steps = {
        "human_offer": "Preguntar si desea atención humana; no transferir."
    }
    if comparisons:
        next_steps["compare_options"] = (
            "Preguntar si desea comparar las opciones mediante los claims "
            "comparativos autorizados, sin prometer acciones externas."
        )
    return ValidatedResponseContext(
        context_id=context_id,
        customer_needs=needs,
        business_facts=facts,
        authorized_claims=claims,
        validated_relationships=relationships,
        # Generic attributes have no typed money/currency/freshness contract.
        # Do not infer commercial comparisons from free-form labels.
        authorized_comparisons=comparisons,
        uncertainties={
            "insufficient_information": (
                "No hay información autorizada suficiente " "para afirmar más."
            )
        },
        allowed_questions=[
            AllowedQuestion(id=f"question_{n.key}", need_key=n.key, purpose=n.question)
            for n in config.needs
            if n.key not in memory
        ],
        allowed_next_steps=next_steps,
        products=products,
        canonical_values=values,
        canonical_clauses=clauses,
    )
