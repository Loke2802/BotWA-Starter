from abc import ABC, abstractmethod

from app.domain.knowledge.contracts import (
    ResolvedKnowledgeItem,
    ValidatedKnowledgeItem,
)


class KnowledgeValidator(ABC):
    @abstractmethod
    def validate(
        self,
        item: ResolvedKnowledgeItem,
    ) -> ValidatedKnowledgeItem: ...


class QualityValidator(KnowledgeValidator):
    def validate(
        self,
        item: ResolvedKnowledgeItem,
    ) -> ValidatedKnowledgeItem:
        health_score = self._calculate_health_score(item)
        validity_status = "approved" if health_score >= 0.7 else "quarantined"
        return ValidatedKnowledgeItem(
            source_id=item.sources[0] if item.sources else "",
            content=item.content,
            confidence=item.confidence,
            health_score=health_score,
            validity_status=validity_status,
        )

    def _calculate_health_score(self, item: ResolvedKnowledgeItem) -> float:
        if not item.content:
            return 0.0
        if len(item.content) < 10:
            return 0.3
        conf_map = {"high": 1.0, "medium": 0.7, "low": 0.5}
        score = conf_map.get(item.confidence, 0.5)
        return round(score, 2)
