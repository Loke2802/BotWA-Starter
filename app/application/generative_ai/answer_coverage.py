"""Bounded lexical coverage of explicitly named published descriptions.

Titles identify topics, never commercial claims. Only complete, short, explicitly
opted-in source statements may fill an omitted description before render validates
them. This is not semantic intent classification or catalog recommendation.
"""

import re
import unicodedata
from typing import Any

from app.domain.generative_ai.contracts import AdviserResult, KnowledgeQuote
from app.domain.generative_ai.knowledge_expression import allows_paraphrase

EXPLORE_OPTIONS = "¿Cuál de estas opciones te gustaría explorar?"
# Explicit explanation requests need not use punctuation in messaging. This is
# a bounded lexical signal, not an inferred recommendation or general intent model.
EXPLANATION_REQUEST = re.compile(
    r"\b(?:explicame|explicanos|explain|quiero (?:entender|saber)|"
    r"(?:que|como) (?:(?:me|nos) )?"
    r"(?:aporta|aportan|ayuda|ayudan|ayudaria|ayudarian|sirve|sirven))\b"
)
STOP_WORDS = {
    "que",
    "qué",
    "una",
    "unas",
    "unos",
    "para",
    "por",
    "con",
    "del",
    "las",
    "los",
    "como",
    "cómo",
    "cada",
    "esta",
    "este",
    "esto",
    "cual",
    "cuál",
    "quiero",
    "quisiera",
    "puedes",
    "puede",
    "aporta",
    "aportan",
    "explicame",
    "explícame",
    "favor",
    "antes",
    "despues",
    "después",
    "poder",
    "decidir",
    "sigo",
    "negocio",
}


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def normalized(text: str) -> str:
    plain = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return " ".join(words(plain))


def retrieval_words(terms: list[str], customer_text: str) -> list[str]:
    # Bounded current-turn terms precede model suggestions. Keep accented input
    # for the existing database ILIKE semantics; normalization only deduplicates.
    result: list[str] = []
    seen: set[str] = set()
    for word in words(customer_text) + [w for t in terms for w in words(t)]:
        key = normalized(word)
        if len(word) > 2 and word not in STOP_WORDS and key not in seen:
            seen.add(key)
            result.append(word[:50])
        if len(result) == 24:
            break
    return result


def requested_descriptions(text: str, sources: dict[str, dict[str, Any]]) -> list[str]:
    # Only a positive request naming exactly two unambiguous multiword labels
    # of the form "Subject: ...". Negation/overlap/ambiguity fail closed. Generic
    # questions, aliases, implicit subjects and recommendations stay with Luna.
    turn = normalized(text)
    if (
        ("?" not in text and EXPLANATION_REQUEST.search(turn) is None)
        or set(turn.split()).intersection(
            {"no", "sin", "not", "without", "nunca", "never"}
        )
        or re.search(r"\b(?:don t|dont)\b", turn)
    ):
        return []
    matches: list[tuple[int, int, str]] = []
    for ref, source in sources.items():
        label, separator, _ = str(source.get("title", "")).partition(":")
        label = normalized(label)
        if (
            not separator
            or not 2 <= len(label.split()) <= 6
            or len(label) > 80
            or source.get("catalog")
            or not allows_paraphrase(
                source["content"], source.get("response_expression")
            )
            or "?" in source["content"]
            or "¿" in source["content"]
        ):
            continue
        position = (" " + turn + " ").find(" " + label + " ")
        if position >= 0:
            matches.append((position, position + len(label), ref))
    matches.sort()
    if len(matches) != 2 or matches[0][1] >= matches[1][0]:
        return []
    return [m[2] for m in matches]


def complete_descriptions(
    result: AdviserResult, refs: list[str], sources: dict[str, dict[str, Any]]
) -> AdviserResult:
    if len(refs) != 2 or result.handoff_requested:
        return result
    if any(
        ref not in sources
        or sources[ref].get("catalog")
        or not allows_paraphrase(
            sources[ref]["content"], sources[ref].get("response_expression")
        )
        for ref in refs
    ):
        return result
    # No price/product/attribute inference and no generated quote rescue. The
    # caller must still run salvage/render and the ordinary source-version fences.
    return result.model_copy(
        update={
            "knowledge": [
                KnowledgeQuote(source_ref=ref, quote=sources[ref]["content"])
                for ref in refs
            ]
        }
    )
