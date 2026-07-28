import re
from abc import ABC, abstractmethod

from app.domain.knowledge.contracts import (
    KnowledgeItem,
    NormalizedKnowledgeItem,
)


class KnowledgeNormalizer(ABC):
    @abstractmethod
    def normalize(
        self,
        items: list[KnowledgeItem],
    ) -> list[NormalizedKnowledgeItem]: ...


class ContentNormalizer(KnowledgeNormalizer):
    def normalize(
        self,
        items: list[KnowledgeItem],
    ) -> list[NormalizedKnowledgeItem]:
        result: list[NormalizedKnowledgeItem] = []
        for item in items:
            content = self._clean_content(item.content)
            result.append(
                NormalizedKnowledgeItem(
                    source_id=item.source_id,
                    canonical_content=content,
                    confidence=item.confidence,
                    source_trust_level=item.source_trust_level,
                    retrieved_at=item.retrieved_at,
                )
            )
        return result

    def _clean_content(self, content: str) -> str:
        content = re.sub(r"<[^>]+>", "", content)
        content = " ".join(content.split())
        return content.strip()
