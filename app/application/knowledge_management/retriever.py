"""Adapt published bot knowledge to the existing Core retrieval contract."""

import re
from uuid import UUID

from app.application.knowledge_management.provider import BotKnowledgeProvider
from app.core.knowledge.retriever import KnowledgeRetriever
from app.domain.knowledge.contracts import KnowledgeItem, KnowledgeQuery
from app.domain.knowledge_management.contracts import KnowledgeEntry

_STOP_WORDS = frozenset(
    [
        "a",
        "al",
        "algo",
        "como",
        "cómo",
        "con",
        "cual",
        "cuál",
        "cuando",
        "cuándo",
        "de",
        "del",
        "el",
        "en",
        "es",
        "esta",
        "está",
        "la",
        "las",
        "lo",
        "los",
        "me",
        "mi",
        "para",
        "por",
        "que",
        "qué",
        "se",
        "son",
        "su",
        "sus",
        "un",
        "una",
        "unos",
        "unas",
        "y",
        "yo",
        "hay",
        "tienen",
        "tiene",
        "quiero",
        "necesito",
        "saber",
        "favor",
        "porfavor",
    ]
)


class PublishedBotKnowledgeRetriever(KnowledgeRetriever):
    def __init__(
        self, provider: BotKnowledgeProvider, organization_id: UUID, bot_id: UUID
    ) -> None:
        self._provider = provider
        self._organization_id = organization_id
        self._bot_id = bot_id

    def retrieve(self, query: KnowledgeQuery) -> list[KnowledgeItem]:
        if query.company_id != str(self._organization_id):
            raise ValueError("knowledge scope mismatch")
        # Bounded lexical retrieval; never fall back to another tenant or seed catalog.
        terms = list(
            dict.fromkeys(
                term
                for term in re.findall(r"[^\W_]+", query.content.casefold())
                if len(term) > 2 and term not in _STOP_WORDS
            )
        )[:8]
        matches: dict[UUID, tuple[KnowledgeEntry, int]] = {}
        for term in terms:
            for entry in self._provider.retrieve_published(
                self._organization_id, self._bot_id, search=term, limit=20
            ):
                if (
                    entry.organization_id != self._organization_id
                    or entry.bot_id != self._bot_id
                    or entry.status != "published"
                ):
                    raise ValueError("knowledge scope mismatch")
                previous = matches.get(entry.id)
                matches[entry.id] = (entry, (previous[1] if previous else 0) + 1)
        ranked = sorted(matches.values(), key=lambda item: (-item[1], str(item[0].id)))
        # The Core selects one answer. Preserve lexical ranking rather than inventing
        # confidence differences for equally authoritative published sources.
        return [
            KnowledgeItem(
                source_id=str(entry.id), content=entry.content, confidence="high"
            )
            for entry, _score in ranked[:1]
        ]
