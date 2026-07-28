from uuid import uuid4

import pytest
from app.infrastructure.database import Base
from app.infrastructure.models.knowledge_catalog_entry import (
    KnowledgeCatalogEntryModel,
)
from app.infrastructure.models.knowledge_query_log import KnowledgeQueryLogModel
from app.infrastructure.models.knowledge_source import KnowledgeSourceModel
from app.infrastructure.repositories.knowledge_catalog_repository import (
    KnowledgeCatalogRepository,
)
from app.infrastructure.repositories.knowledge_query_log_repository import (
    KnowledgeQueryLogRepository,
)
from app.infrastructure.repositories.knowledge_source_repository import (
    KnowledgeSourceRepository,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine)()
    return test_session


class TestKnowledgeSourceRepository:
    def test_add_and_get(self, session: Session) -> None:
        repo = KnowledgeSourceRepository(session=session)
        src_id = uuid4()
        src = KnowledgeSourceModel(
            id=src_id,
            source_id="test-source",
            name="Test Source",
            type="manual",
        )
        repo.add(src)
        session.commit()

        retrieved = repo.get(src_id)
        assert retrieved is not None
        assert retrieved.source_id == "test-source"
        assert retrieved.name == "Test Source"

    def test_get_not_found(self, session: Session) -> None:
        repo = KnowledgeSourceRepository(session=session)
        assert repo.get(uuid4()) is None

    def test_list_sources(self, session: Session) -> None:
        repo = KnowledgeSourceRepository(session=session)
        for i in range(3):
            repo.add(
                KnowledgeSourceModel(
                    id=uuid4(),
                    source_id=f"src-{i}",
                    name=f"Source {i}",
                    type="manual",
                )
            )
        session.commit()

        results = repo.list()
        assert len(results) == 3


class TestKnowledgeCatalogRepository:
    def test_add_and_get(self, session: Session) -> None:
        repo = KnowledgeCatalogRepository(session=session)
        entry_id = uuid4()
        entry = KnowledgeCatalogEntryModel(
            id=entry_id,
            source_id="seed",
            keywords="horario,atención",
            content="Test content",
            confidence="high",
            source_trust_level=0.9,
        )
        repo.add(entry)
        session.commit()

        retrieved = repo.get(entry_id)
        assert retrieved is not None
        assert retrieved.content == "Test content"
        assert retrieved.source_trust_level == 0.9

    def test_search_by_keywords_found(self, session: Session) -> None:
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
        repo.add(
            KnowledgeCatalogEntryModel(
                id=uuid4(),
                source_id="seed",
                keywords="pago,tarjeta,transferencia",
                content="Aceptamos tarjetas",
                confidence="high",
            )
        )
        session.commit()

        results = repo.search_by_keywords("¿Cuál es el horario?")
        assert len(results) == 1
        assert "horario" in results[0].content.lower()

    def test_search_by_keywords_not_found(self, session: Session) -> None:
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

        results = repo.search_by_keywords("something completely different")
        assert len(results) == 0


class TestKnowledgeQueryLogRepository:
    def test_add_and_get(self, session: Session) -> None:
        repo = KnowledgeQueryLogRepository(session=session)
        log_id = uuid4()
        log = KnowledgeQueryLogModel(
            id=log_id,
            query_text="¿Cuál es el horario?",
            intent="question",
            response_found=True,
        )
        repo.add(log)
        session.commit()

        retrieved = repo.get(log_id)
        assert retrieved is not None
        assert retrieved.query_text == "¿Cuál es el horario?"
        assert retrieved.response_found is True
