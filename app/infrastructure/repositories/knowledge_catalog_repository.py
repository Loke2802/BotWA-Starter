from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models.knowledge_catalog_entry import (
    KnowledgeCatalogEntryModel,
)
from app.infrastructure.repositories.base import BaseRepository


class KnowledgeCatalogRepository(BaseRepository[KnowledgeCatalogEntryModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, KnowledgeCatalogEntryModel)

    def search_by_keywords(self, query_text: str) -> list[KnowledgeCatalogEntryModel]:
        stmt = select(KnowledgeCatalogEntryModel).where(
            KnowledgeCatalogEntryModel.valid_until.is_(None),
        )
        results: list[KnowledgeCatalogEntryModel] = list(
            self._session.scalars(stmt).all(),
        )
        text = query_text.lower()
        matched: list[KnowledgeCatalogEntryModel] = []
        for entry in results:
            keywords = [
                kw.strip().lower() for kw in entry.keywords.split(",") if kw.strip()
            ]
            if any(kw in text for kw in keywords):
                matched.append(entry)
        return matched

    def find_by_source_id(
        self,
        source_id: str,
    ) -> list[KnowledgeCatalogEntryModel]:
        stmt = select(KnowledgeCatalogEntryModel).where(
            KnowledgeCatalogEntryModel.source_id == source_id,
        )
        return list(self._session.scalars(stmt).all())
