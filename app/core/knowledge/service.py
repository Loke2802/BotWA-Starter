from datetime import UTC, datetime

from app.core.knowledge.normalizer import KnowledgeNormalizer
from app.core.knowledge.publisher import KnowledgePublisher
from app.core.knowledge.resolver import KnowledgeResolver
from app.core.knowledge.retriever import KnowledgeRetriever
from app.core.knowledge.validator import KnowledgeValidator
from app.domain.knowledge.contracts import (
    KnowledgeQuery,
    KnowledgeResponse,
)
from app.infrastructure.models.knowledge_query_log import KnowledgeQueryLogModel
from app.infrastructure.repositories.knowledge_query_log_repository import (
    KnowledgeQueryLogRepository,
)


class KnowledgeService:
    def __init__(
        self,
        retriever: KnowledgeRetriever,
        normalizer: KnowledgeNormalizer,
        resolver: KnowledgeResolver,
        validator: KnowledgeValidator,
        publisher: KnowledgePublisher,
        query_log_repository: KnowledgeQueryLogRepository | None = None,
    ) -> None:
        self._retriever = retriever
        self._normalizer = normalizer
        self._resolver = resolver
        self._validator = validator
        self._publisher = publisher
        self._query_log_repo = query_log_repository

    def query(self, query: KnowledgeQuery) -> KnowledgeResponse:
        start = datetime.now(UTC)
        items = self._retriever.retrieve(query)
        if not items:
            self._log_query(query, found=False, latency_ms=0)
            return KnowledgeResponse(found=False)
        normalized = self._normalizer.normalize(items)
        resolved = self._resolver.resolve(normalized)
        validated = self._validator.validate(resolved)
        response = self._publisher.publish(validated)
        latency = int((datetime.now(UTC) - start).total_seconds() * 1000)
        self._log_query(query, response.found, latency, response.sources)
        return response

    def _log_query(
        self,
        query: KnowledgeQuery,
        found: bool,
        latency_ms: int,
        sources: list[str] | None = None,
    ) -> None:
        if self._query_log_repo is None:
            return
        log = KnowledgeQueryLogModel(
            query_text=query.content,
            intent=query.intent,
            response_found=found,
            response_source=sources[0] if sources else None,
            latency_ms=latency_ms,
        )
        self._query_log_repo.add(log)
