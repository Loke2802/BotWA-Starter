from app.core.knowledge.db_catalog import DbKnowledgeCatalog
from app.core.knowledge.retriever import KnowledgeRetriever
from app.domain.knowledge.contracts import KnowledgeItem, KnowledgeQuery


class DbKnowledgeRetriever(KnowledgeRetriever):
    def __init__(self, catalog: DbKnowledgeCatalog) -> None:
        self._catalog = catalog

    def retrieve(self, query: KnowledgeQuery) -> list[KnowledgeItem]:
        return self._catalog.search(query)
