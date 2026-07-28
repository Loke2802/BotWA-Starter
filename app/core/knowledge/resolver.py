from abc import ABC, abstractmethod
from datetime import UTC, datetime

from app.domain.knowledge.contracts import (
    NormalizedKnowledgeItem,
    ResolvedKnowledgeItem,
)


class KnowledgeResolver(ABC):
    @abstractmethod
    def resolve(
        self,
        items: list[NormalizedKnowledgeItem],
    ) -> ResolvedKnowledgeItem: ...


class BestMatchResolver(KnowledgeResolver):
    def resolve(
        self,
        items: list[NormalizedKnowledgeItem],
    ) -> ResolvedKnowledgeItem:
        if not items:
            return ResolvedKnowledgeItem(
                content="",
                resolution_strategy="best_match",
            )

        scored = [(self._score(item), item) for item in items]
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = scored[0][1]

        return ResolvedKnowledgeItem(
            sources=[item.source_id for item in items],
            content=selected.canonical_content,
            confidence=selected.confidence,
            resolution_strategy="best_match",
        )

    def _score(self, item: NormalizedKnowledgeItem) -> float:
        trust = item.source_trust_level
        now = datetime.now(UTC)
        age_hours = (now - item.retrieved_at).total_seconds() / 3600
        freshness = max(0.0, 1.0 - (age_hours / 24.0))
        conf_map = {"high": 1.0, "medium": 0.6, "low": 0.3}
        conf = conf_map.get(item.confidence, 0.3)
        return round(trust * 0.4 + freshness * 0.2 + conf * 0.4, 4)
