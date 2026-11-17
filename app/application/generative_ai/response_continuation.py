"""Bounded continuity after rejection; no generated text gains authority here."""

import re
import unicodedata
from typing import Any

from app.application.generative_ai.answer_coverage import (
    EXPLORE_OPTIONS,
    requested_descriptions,
)
from app.application.generative_ai.validation import render
from app.domain.generative_ai.contracts import AdviserResult, AIConfig, ProviderError
from app.domain.generative_ai.knowledge_expression import allows_paraphrase

HUMAN_OFFER = "¿Quieres que un asesor te ayude a definir el siguiente paso?"
CLARIFY_REQUEST = "¿Qué detalle necesitas aclarar para continuar con tu proyecto?"
UNCONFIRMED = "No puedo confirmar ese detalle con la información disponible."
PRICE_UNCONFIRMED = "No tengo confirmado el precio exacto de tu proyecto."
PRICE_REQUEST = re.compile(
    r"\b(?:cu[aá]nto\s+(?:cuesta|costar[ií]a|vale|saldr[ií]a)|"
    r"(?:cu[aá]l|qu[eé])\s+(?:(?:es|ser[ií]a)\s+)?(?:el\s+)?(?:precio|costo|coste)|"
    r"(?:dime|ind[ií]came)\s+(?:el\s+)?(?:precio|costo|coste))\b",
    re.I,
)
DESCRIPTION_REQUEST = re.compile(
    r"\b(?:incluye|incluyen|ofrece|ofrecen|aporta|aportan|sirve|sirven|funciona|"
    r"funcionan|diferencias?|ventajas?|beneficios?|caracter[ií]sticas?)\b",
    re.I,
)
MONETARY_REFERENCE = re.compile(r"(?:S/|\$|PEN\b|USD\b|EUR\b)\s*\d", re.I)
STOP_REQUESTS = {
    "no me interesa",
    "no quiero continuar",
    "no me contactes",
    "no me escribas",
    "no insistas",
    "deja de escribir",
}
QUESTION_REFUSAL = re.compile(
    r"\b(?:no\s+(?:(?:me\s+)?(?:hagas|hag[aá]is)\s+)?m[aá]s\s+preguntas|"
    r"no\s+(?:quiero|deseo)\s+(?:m[aá]s\s+preguntas|responder)|"
    r"no\s+(?:me\s+)?preguntes|sin\s+(?:m[aá]s\s+)?preguntas|"
    r"no\s+more\s+questions|don.t\s+ask)\b",
    re.I,
)


def declines_questions(text: str) -> bool:
    return bool(QUESTION_REFUSAL.search(text))


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
    selected = {q.source_ref: sources[q.source_ref] for q in result.knowledge}
    explaining_options = bool(requested_descriptions(customer_text, selected))
    # Descriptive permission excludes monetary facts. Repeating a definition
    # cannot answer a price-only question. Catalog amounts keep their own path.
    price_only = (
        bool(PRICE_REQUEST.search(customer_text))
        and not explaining_options
        and not DESCRIPTION_REQUEST.search(customer_text)
        and not result.recommendations
        and all(
            allows_paraphrase(
                sources[q.source_ref]["content"],
                sources[q.source_ref].get("response_expression"),
            )
            for q in result.knowledge
        )
    )
    facts: list[str] = [PRICE_UNCONFIRMED] if price_only else []
    if result.recommendations:
        catalog_text, _ = render(
            result.model_copy(update={"question_key": None, "knowledge": []}),
            config,
            memory,
            sources,
        )
        facts.append(catalog_text)
    for quote in result.knowledge:
        source = sources[quote.source_ref]
        literal_price = (
            config.qualify_for_proposal
            and bool(PRICE_REQUEST.search(customer_text))
            and bool(MONETARY_REFERENCE.search(quote.quote))
        )
        if (
            not price_only
            and not source.get("catalog")
            and (
                literal_price
                or allows_paraphrase(
                    source["content"], source.get("response_expression")
                )
            )
            and not any(mark in quote.quote for mark in ("?", "¿"))
        ):
            # render() above already checked the complete literal source quote.
            # Qualification can retain that entire selected price clause with
            # all conditions; it never rescues rejected generated price prose.
            facts.append(quote.quote)
    # Selected, revalidated facts still answer this turn even if stated before.
    # History may suppress a repeated question/offer, never veto business evidence
    # and turn a known fact into a claim that no information is available.
    if config.qualify_for_proposal and declines_questions(customer_text):
        answer = "\n\n".join(facts) or UNCONFIRMED
        if len(answer) <= limit:
            return answer
        if len(UNCONFIRMED) <= limit:
            return UNCONFIRMED
        raise ProviderError("RESPONSE_LENGTH")
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
    if explaining_options and not already_said(EXPLORE_OPTIONS, recent):
        next_step = EXPLORE_OPTIONS
    elif explaining_options and not pending:
        next_step = (
            "Puedes indicarme cuál de estas opciones deseas explorar "
            "cuando estés listo."
        )
    elif pending:
        next_step = pending
    elif not config.qualify_for_proposal and not already_said(HUMAN_OFFER, recent):
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
