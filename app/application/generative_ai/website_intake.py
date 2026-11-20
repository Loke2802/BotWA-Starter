"""Explicit website enquiries that can be handled without model inference."""

import re
from typing import Any

from app.application.generative_ai.response_continuation import (
    MONETARY_REFERENCE,
    PRICE_REQUEST,
    normalized,
)
from app.domain.generative_ai.contracts import AdviserResult

_GREETING = r"(?:(?:hola|buenas|buenos d[ií]as|buenas tardes|buenas noches) )?"
_OPENING = re.compile(
    _GREETING + r"(?:hola|buenas|buenos d[ií]as|buenas tardes|buenas noches|"
    r"(?:quiero|quisiera|necesito|deseo) (?:m[aá]s )?(?:info|informaci[oó]n)|"
    r"(?:quiero|quisiera|necesito|deseo|busco|me interesa) "
    r"(?:(?:cotizar|hacer|crear|dise[nñ]ar) (?:el dise[nñ]o de )?)?"
    r"(?:(?:un|una|mi|el|la) )?(?:p[aá]gina web|sitio web|web|landing(?: page)?)"
    r"(?: para (?:mi|un) negocio)?)(?: por favor)?"
)
_PROMO_OPENING = re.compile(
    _GREETING + r"me interesa (?:la|una) (?:p[aá]gina )?web con branding(?: b[aá]sico)?"
    r"(?: desde s \d{1,7}(?: sin igv)?)?(?: mi negocio es)?"
)
_PRICE_OPENING = re.compile(
    _GREETING + r"cu[aá]nto (?:cuesta|costar[ií]a|vale|sale) "
    r"(?:(?:un|una|el|la) )?(?:p[aá]gina web|sitio web|web|landing(?: page)?)"
    r"(?: para (?:mi|un) negocio)?(?: por favor)?"
)
_LOAN_REQUEST = re.compile(
    _GREETING + r"(?:(?:(?:yo )?(?:quiero|quisiera|necesito|busco|solicito|deseo) "
    r"(?:(?:solicitar|pedir|tramitar) )?(?:un )?|"
    r"(?:tienen|ofrecen|dan) |(?:informaci[oó]n|info) (?:de|sobre) )?"
    r"(?:pr[eé]stamos?|cr[eé]dito (?:personal|de dinero))\b|"
    r"(?:me (?:puedes|pueden) prestar|prestan) dinero\b)"
)
_WEBSITE_CONTEXT = re.compile(
    r"\b(?:web|landing|cat[aá]logo|tienda online|dise[nñ]o|desarrollo|"
    r"mercadotecnia|marketing|prestamos servicios)\b"
)
_PRICE_WORD = re.compile(
    r"\b(?:precios?|costos?|costes?|inversi[oó]n|tarifas?|importes?)\b", re.I
)
_MONEY_SUFFIX = re.compile(r"\b\d[\d.,]*\s+(?:soles|d[oó]lares|euros)\b", re.I)
_OPENING_REPLY = (
    "Para ayudarte a elegir una web que le sirva a tu negocio, cuéntame un poco. "
    "¿A qué se dedica tu empresa y qué te gustaría lograr con tu página? "
    "Por ejemplo, mostrar tus servicios, recibir consultas por WhatsApp o vender "
    "en línea."
)
_LOAN_REPLY = "Aquí atendemos consultas sobre diseño web para negocios."


def website_intake_reply(
    customer_text: str,
    *,
    first_reply: bool,
    business_known: bool,
) -> str | None:
    text = normalized(customer_text)
    if first_reply and _LOAN_REQUEST.match(text) and not _WEBSITE_CONTEXT.search(text):
        return _LOAN_REPLY
    if (
        first_reply
        and not business_known
        and any(
            opening.fullmatch(text)
            for opening in (_OPENING, _PROMO_OPENING, _PRICE_OPENING)
        )
    ):
        return _OPENING_REPLY
    return None


def omit_unrequested_prices(
    result: AdviserResult, customer_text: str, sources: dict[str, dict[str, Any]]
) -> AdviserResult:
    if PRICE_REQUEST.search(customer_text) or _PRICE_WORD.search(customer_text):
        return result

    def has_price(text: str) -> bool:
        return bool(
            MONETARY_REFERENCE.search(text)
            or _MONEY_SUFFIX.search(text)
            or _PRICE_WORD.search(text)
        )

    recommendations = []
    for recommendation in result.recommendations:
        source = sources.get(recommendation.item_ref, {})
        catalog = source.get("catalog") or {}
        matched_keys = {match.attribute_key for match in recommendation.matches}
        if not any(
            attribute.get("key") in matched_keys
            and has_price(f"{attribute.get('label', '')} {attribute.get('value', '')}")
            for attribute in catalog.get("attributes", [])
        ):
            recommendations.append(recommendation)
    return result.model_copy(
        update={
            "recommendations": recommendations,
            "knowledge": [
                quote for quote in result.knowledge if not has_price(quote.quote)
            ],
        }
    )
