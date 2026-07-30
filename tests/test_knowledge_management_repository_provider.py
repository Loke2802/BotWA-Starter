from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.application.knowledge_management.provider import BotKnowledgeProvider
from app.infrastructure.database import Base
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.repositories.knowledge_entry_repository import (
    InMemoryKnowledgeEntryRepository,
    SqlAlchemyKnowledgeEntryRepository,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def make_entry(
    organization_id: UUID,
    bot_id: UUID,
    status: str,
    title: str,
    *,
    created_offset: int = 0,
) -> KnowledgeEntryModel:
    return KnowledgeEntryModel(
        id=uuid4(),
        organization_id=organization_id,
        bot_id=bot_id,
        title=title,
        content=f"{title} content",
        status=status,
        source_type="manual",
        metadata_data={},
        created_by_user_id=uuid4(),
        created_at=datetime.now(UTC) + timedelta(seconds=created_offset),
        updated_at=datetime.now(UTC),
    )


def test_isolated_provider_returns_only_published_scope() -> None:
    repository = InMemoryKnowledgeEntryRepository()
    organization_id = uuid4()
    bot_id = uuid4()
    repository.add(make_entry(organization_id, bot_id, "published", "Visible"))
    repository.add(make_entry(organization_id, bot_id, "draft", "Draft"))
    repository.add(make_entry(organization_id, bot_id, "archived", "Archived"))
    repository.add(make_entry(organization_id, uuid4(), "published", "Other bot"))
    repository.add(make_entry(uuid4(), bot_id, "published", "Other tenant"))

    entries = BotKnowledgeProvider(repository).retrieve_published(
        organization_id,
        bot_id,
    )

    assert [entry.title for entry in entries] == ["Visible"]


def test_sql_repository_filters_and_paginates_in_database() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repository = SqlAlchemyKnowledgeEntryRepository(session)
    organization_id = uuid4()
    bot_id = uuid4()
    repository.add(
        make_entry(organization_id, bot_id, "draft", "First match", created_offset=1),
    )
    repository.add(
        make_entry(organization_id, bot_id, "draft", "Second match", created_offset=2),
    )
    repository.add(
        make_entry(organization_id, bot_id, "published", "Published", created_offset=3),
    )
    repository.add(make_entry(uuid4(), bot_id, "draft", "Other tenant"))
    session.commit()

    page = repository.list_scoped(
        organization_id,
        bot_id,
        status="draft",
        search="match",
        offset=1,
        limit=1,
    )

    assert [entry.title for entry in page] == ["Second match"]
    assert (
        repository.count_scoped(
            organization_id,
            bot_id,
            status="draft",
            search="match",
        )
        == 2
    )
    session.close()
