"""Bounded continuity after rejection; no generated text gains authority here."""

import re
import unicodedata
from typing import Any

from app.application.generative_ai.validation import render
from app.domain.generative_ai.contracts import AdviserResult, AIConfig, ProviderError
from app.domain.generative_ai.knowledge_expression import allows_paraphrase

HUMAN_OFFER = "¿Quieres que un asesor te ayude a definir el siguiente paso?"
CLARIFY_REQUEST = "¿Qué detalle necesitas aclarar para continuar con tu proyecto?"
UNCONFIRMED = "No puedo confirmar ese detalle con la información disponible."
STOP_REQUESTS = {
    "no me interesa",
    "no quiero continuar",
    "no me contactes",
    "no me escribas",
    "no insistas",
    "deja de escribir",
}


def normalized(text: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def already_said(text: str, recent_responses: list[str]) -> bool:
    needle = normalized(text)
    return bool(needle) and any(needle in normalized(t) for t in recent_responses)


def recent_responses(history: list[dict[str, Any]]) -> list[str]:
    # This is the already-scoped, encrypted snapshot. Old assistant/human prose
    # is context for repetition checks, never evidence for commercial facts.
    return [
        str(m["text"])[:1200]
        for m in history
        if m.get("direction") == "outbound" and m.get("text")
    ][-3:]


def safe_continuation(
    result: AdviserResult,
    config: AIConfig,
    memory: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    recent: list[str],
    customer_text: str = "",
    max_chars: int = 3500,
) -> str:
    # Revalidate every selected reference, exact quote and catalog requirement.
    # Do not retrieve another source or rescue prose rejected by the reviewer.
    render(result, config, memory, sources)
    limit = min(3500, max_chars)
    # A conversational acknowledgement, not a persistent unsubscribe record.
    # Whole-message matches do not swallow "not this option, I want another".
    if normalized(customer_text).removesuffix(" gracias") in STOP_REQUESTS:
        acknowledgement = "De acuerdo. Gracias por indicarlo."
        if len(acknowledgement) > limit:
            raise ProviderError("RESPONSE_LENGTH")
        return acknowledgement
    facts: list[str] = []
    if result.recommendations:
        catalog_text, _ = render(
            result.model_copy(update={"question_key": None, "knowledge": []}),
            config,
            memory,
            sources,
        )
        if not already_said(catalog_text, recent):
            facts.append(catalog_text)
    for quote in result.knowledge:
        source = sources[quote.source_ref]
        if (
            not source.get("catalog")
            and allows_paraphrase(source["content"], source.get("response_expression"))
            and not any(mark in quote.quote for mark in ("?", "¿"))
            and not already_said(quote.quote, recent)
        ):
            # The exceptional path uses the original short descriptive fact.
            # No paraphrase, inferred benefit, price or new promise is inserted.
            facts.append(quote.quote)
    pending = next(
        (
            n.question
            for n in config.needs
            if n.key not in memory
            and not already_said(n.question, recent)
            and n.question.count("?") <= 1
            and n.question.count("¿") <= 1
        ),
        None,
    )
    if pending:
        next_step = pending
    elif not already_said(HUMAN_OFFER, recent):
        next_step = HUMAN_OFFER
    elif not already_said(CLARIFY_REQUEST, recent):
        next_step = CLARIFY_REQUEST
    else:
        next_step = (
            "Puedes indicarme el detalle que falta resolver cuando desees continuar."
        )
    if not facts and not pending:
        facts.append(UNCONFIRMED)
    # Facts from two short sources and at most one bounded next step. Catalog
    # clauses cannot be truncated midway through a protected condition.
    text = "\n\n".join([*facts, next_step])
    if len(text) > limit or text.count("?") > 1 or text.count("¿") > 1:
        bounded = "\n\n".join([UNCONFIRMED, next_step])
        if len(bounded) <= limit:
            return bounded
        if len(next_step) <= limit:
            return next_step
        raise ProviderError("RESPONSE_LENGTH")
    return text
