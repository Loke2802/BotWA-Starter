from uuid import uuid4

import pytest
from app.core.knowledge.db_catalog import DbKnowledgeCatalog
from app.core.knowledge.db_retriever import DbKnowledgeRetriever
from app.core.knowledge.publisher import DbKnowledgePublisher
from app.core.knowledge.seed_data import ensure_knowledge_seed_data
from app.domain.knowledge.contracts import (
    KnowledgeQuery,
    ValidatedKnowledgeItem,
)
from app.infrastructure.database import Base
from app.infrastructure.models.knowledge_catalog_entry import (
    KnowledgeCatalogEntryModel,
)
from app.infrastructure.repositories.knowledge_catalog_repository import (
    KnowledgeCatalogRepository,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine)()
    return test_session


class TestDbKnowledgeCatalog:
    def test_search_found(self, session: Session) -> None:
        repo = KnowledgeCatalogRepository(session=session)
        repo.add(
            KnowledgeCatalogEntryModel(
                id=uuid4(),
                source_id="seed",
                keywords="horario,atención,abren",
                content="Nuestro horario es de 9 a 18",
                confidence="high",
            )
        )
        session.commit()

        catalog = DbKnowledgeCatalog(catalog_repository=repo)
        query = KnowledgeQuery(
            content="¿Cuál es el horario?",
            intent="question",
        )
        results = catalog.search(query)

        assert len(results) == 1
        assert "horario" in results[0].content.lower()

    def test_search_not_found(self, session: Session) -> None:
        repo = KnowledgeCatalogRepository(session=session)
        repo.add(
            KnowledgeCatalogEntryModel(
                id=uuid4(),
                source_id="seed",
                keywords="horario,atención",
                content="Test",
                confidence="low",
            )
        )
        session.commit()

        catalog = DbKnowledgeCatalog(catalog_repository=repo)
        query = KnowledgeQuery(
            content="no match here",
            intent="unknown",
        )
        results = catalog.search(query)

        assert len(results) == 0

    def test_search_propagates_trust_level(self, session: Session) -> None:
        repo = KnowledgeCatalogRepository(session=session)
        repo.add(
            KnowledgeCatalogEntryModel(
                id=uuid4(),
                source_id="seed",
                keywords="horario,atención",
                content="Nuestro horario es de 9 a 18",
                confidence="high",
                source_trust_level=0.8,
            )
        )
        session.commit()

        catalog = DbKnowledgeCatalog(catalog_repository=repo)
        query = KnowledgeQuery(
            content="¿Cuál es el horario?",
            intent="question",
        )
        results = catalog.search(query)

        assert len(results) == 1
        assert results[0].source_trust_level == 0.8


class TestDbKnowledgeRetriever:
    def test_retrieve_found(self, session: Session) -> None:
        repo = KnowledgeCatalogRepository(session=session)
        repo.add(
            KnowledgeCatalogEntryModel(
                id=uuid4(),
                source_id="seed",
                keywords="horario,atención",
                content="Nuestro horario de atención",
                confidence="high",
            )
        )
        session.commit()

        catalog = DbKnowledgeCatalog(catalog_repository=repo)
        retriever = DbKnowledgeRetriever(catalog=catalog)
        query = KnowledgeQuery(
            content="¿Cuál es el horario?",
            intent="question",
        )
        items = retriever.retrieve(query)

        assert len(items) == 1
        assert items[0].source_id == "seed"
        assert items[0].confidence == "high"

    def test_retrieve_not_found(self, session: Session) -> None:
        repo = KnowledgeCatalogRepository(session=session)
        repo.add(
            KnowledgeCatalogEntryModel(
                id=uuid4(),
                source_id="seed",
                keywords="horario",
                content="Test",
                confidence="low",
            )
        )
        session.commit()

        catalog = DbKnowledgeCatalog(catalog_repository=repo)
        retriever = DbKnowledgeRetriever(catalog=catalog)
        query = KnowledgeQuery(
            content="completely unrelated",
            intent="unknown",
        )
        items = retriever.retrieve(query)

        assert items == []


class TestDbKnowledgePublisher:
    def test_publish_persists_to_catalog(self, session: Session) -> None:
        repo = KnowledgeCatalogRepository(session=session)
        publisher = DbKnowledgePublisher(catalog_repository=repo)
        item = ValidatedKnowledgeItem(
            source_id="test-source",
            content="Published content",
            confidence="high",
        )

        response = publisher.publish(item)

        assert response.found is True
        session.commit()
        all_entries = repo.list()
        assert len(all_entries) == 1
        assert all_entries[0].content == "Published content"

    def test_publish_not_found_does_not_persist(self, session: Session) -> None:
        repo = KnowledgeCatalogRepository(session=session)
        publisher = DbKnowledgePublisher(catalog_repository=repo)
        item = ValidatedKnowledgeItem(content="")

        response = publisher.publish(item)

        assert response.found is False
        all_entries = repo.list()
        assert len(all_entries) == 0

    def test_publish_tracks_version(self, session: Session) -> None:
        repo = KnowledgeCatalogRepository(session=session)
        publisher = DbKnowledgePublisher(catalog_repository=repo)
        v1 = ValidatedKnowledgeItem(
            source_id="src-ver",
            content="First version",
            confidence="high",
        )
        v2 = ValidatedKnowledgeItem(
            source_id="src-ver",
            content="Second version",
            confidence="high",
        )

        r1 = publisher.publish(v1)
        r2 = publisher.publish(v2)

        assert r1.version == 1
        assert r2.version == 2
        session.commit()
        entries = repo.find_by_source_id("src-ver")
        assert len(entries) == 2


class TestKnowledgeSeedData:
    def test_seed_data_inserts_on_empty_catalog(self, session: Session) -> None:
        repo = KnowledgeCatalogRepository(session=session)
        ensure_knowledge_seed_data(repo)
        session.commit()

        all_entries = repo.list()
        assert len(all_entries) == 4

    def test_seed_data_skips_if_not_empty(self, session: Session) -> None:
        repo = KnowledgeCatalogRepository(session=session)
        repo.add(
            KnowledgeCatalogEntryModel(
                id=uuid4(),
                source_id="existing",
                keywords="test",
                content="Existing item",
                confidence="low",
            )
        )
        session.commit()

        ensure_knowledge_seed_data(repo)
        session.commit()

        all_entries = repo.list()
        assert len(all_entries) == 1
