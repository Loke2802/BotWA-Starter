import re
from typing import Any

from app.domain.generative_ai.contracts import (
    AdviserResult,
    AIConfig,
    CatalogItem,
    Discovery,
    NeedDefinition,
    ProviderError,
)

FALLBACK = "Ahora no puedo comprobar esa información. Inténtalo de nuevo más tarde."


def apply_discovery(
    discovery: Discovery,
    config: AIConfig,
    memory: dict[str, Any],
    messages: dict[str, str],
) -> dict[str, Any]:
    result = {} if discovery.new_topic else dict(memory)
    definitions = {item.key: item for item in config.needs}
    ordering = {ref: index for index, ref in enumerate(messages)}
    for patch in discovery.needs:
        definition = definitions.get(patch.key)
        source = messages.get(patch.message_ref, "")
        if (
            definition is None
            or patch.quote not in source
            or patch.value.casefold() not in patch.quote.casefold()
        ):
            raise ProviderError("UNSUPPORTED_MEMORY")
        if definition.kind == "number" and not re.fullmatch(
            r"\d+(?:\.\d+)?", patch.value
        ):
            raise ProviderError("INVALID_NEED_TYPE")
        if definition.kind == "number" and patch.value not in re.findall(
            r"(?<![\w.-])\d+(?:\.\d+)?(?![\w.])", patch.quote
        ):
            raise ProviderError("UNSUPPORTED_NUMERIC_EVIDENCE")
        previous = result.get(patch.key)
        if previous and ordering.get(patch.message_ref, -1) < ordering.get(
            previous.get("message_ref", ""), -1
        ):
            raise ProviderError("STALE_MEMORY_EVIDENCE")
        # Evidence-backed extraction is still a hypothesis: the model cannot
        # promote semantics to a confirmed customer profile or consent record.
        result[patch.key] = {
            "value": patch.value,
            "quote": patch.quote,
            "message_ref": patch.message_ref,
            "status": "evidence_backed",
        }
    return result


def compatible(definition: NeedDefinition, value: str, item: CatalogItem) -> bool:
    attribute = next(
        (a for a in item.attributes if a.key == definition.attribute), None
    )
    if attribute is None:
        return False
    if definition.comparison == "equals":
        return value.casefold() == attribute.value.casefold()
    if definition.comparison == "contains":
        return value.casefold() in attribute.value.casefold()
    try:
        number = float(value)
    except ValueError:
        return False
    if definition.comparison == "range":
        return (
            attribute.minimum is not None
            and attribute.maximum is not None
            and attribute.minimum <= number <= attribute.maximum
        )
    return attribute.maximum is not None and attribute.maximum <= number


def render(
    result: AdviserResult,
    config: AIConfig,
    memory: dict[str, Any],
    sources: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, str]]:
    definitions = {item.key: item for item in config.needs}
    text: list[str] = []
    used: dict[str, str] = {}
    if result.question_key:
        need = definitions.get(result.question_key)
        if need is None or result.question_key in memory:
            raise ProviderError("REPEATED_OR_UNKNOWN_QUESTION")
        text.append(need.question)
    for recommendation in result.recommendations:
        source = sources.get(recommendation.item_ref)
        if source is None or not source.get("catalog"):
            raise ProviderError("UNKNOWN_ITEM")
        item = CatalogItem.model_validate(source["catalog"])
        for required_definition in config.needs:
            if required_definition.required and (
                required_definition.key not in memory
                or not compatible(
                    required_definition, memory[required_definition.key]["value"], item
                )
            ):
                raise ProviderError("MISSING_OR_INCOMPATIBLE_REQUIREMENT")
        reasons = []
        for match in recommendation.matches:
            definition = definitions.get(match.need_key)
            if (
                definition is None
                or match.need_key not in memory
                or definition.attribute != match.attribute_key
                or not compatible(definition, memory[match.need_key]["value"], item)
            ):
                raise ProviderError("UNSUPPORTED_RECOMMENDATION")
            attribute = next(a for a in item.attributes if a.key == match.attribute_key)
            reasons.append(f"{attribute.label}: {attribute.value}")
        text.append(
            f"{item.name}: coincide con lo que buscas. " + "; ".join(reasons) + "."
        )
        used[recommendation.item_ref] = source["version"]
    for quote in result.knowledge:
        source = sources.get(quote.source_ref)
        # Product assertions cannot bypass catalog compatibility via raw quotes.
        if source is None or source.get("catalog") or quote.quote != source["content"]:
            raise ProviderError("UNSUPPORTED_KNOWLEDGE")
        text.append(quote.quote)
        used[quote.source_ref] = source["version"]
    if not text:
        missing = next((n for n in config.needs if n.key not in memory), None)
        text.append(
            missing.question
            if missing
            else (
                "No tengo información suficiente para recomendar "
                "una opción con seguridad."
            )
        )
    introduction = {
        "understood": "Gracias por contármelo.",
        "options": "Estas opciones podrían encajar con lo que buscas:",
        "clarify": "Para orientarte mejor:",
        "unknown": "",
    }[result.tone]
    if introduction and (result.recommendations or result.question_key):
        text.insert(0, introduction)
    return "\n\n".join(text)[:3500], used
