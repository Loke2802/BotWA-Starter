from uuid import uuid4

import pytest
from app.infrastructure.database import Base
from app.infrastructure.models.business_event import BusinessEventModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.repositories.business_event_repository import (
    BusinessEventRepository,
)
from app.infrastructure.repositories.conversation_repository import (
    ConversationRepository,
)
from app.infrastructure.repositories.message_repository import MessageRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine)()
    return test_session


class TestConversationRepository:
    def test_add_and_get(self, session: Session) -> None:
        repo = ConversationRepository(session=session)
        conv_id = uuid4()
        conv = ConversationModel(
            id=conv_id,
            company_id="company-1",
            customer_id="customer-1",
            channel="http",
            status="active",
        )
        repo.add(conv)
        session.commit()

        retrieved = repo.get(conv_id)
        assert retrieved is not None
        assert retrieved.id == conv_id
        assert retrieved.company_id == "company-1"

    def test_get_not_found(self, session: Session) -> None:
        repo = ConversationRepository(session=session)
        assert repo.get(uuid4()) is None

    def test_delete(self, session: Session) -> None:
        repo = ConversationRepository(session=session)
        conv_id = uuid4()
        conv = ConversationModel(
            id=conv_id,
            company_id="company-1",
            customer_id="customer-1",
            channel="http",
            status="active",
        )
        repo.add(conv)
        session.commit()

        assert repo.delete(conv_id) is True
        session.commit()
        assert repo.get(conv_id) is None

    def test_delete_not_found(self, session: Session) -> None:
        repo = ConversationRepository(session=session)
        assert repo.delete(uuid4()) is False


class TestMessageRepository:
    def test_add_and_get(self, session: Session) -> None:
        conv_id = uuid4()
        conv = ConversationModel(
            id=conv_id,
            company_id="c",
            customer_id="c",
            channel="http",
            status="active",
        )
        session.add(conv)
        session.commit()

        repo = MessageRepository(session=session)
        msg_id = uuid4()
        msg = MessageModel(
            id=msg_id,
            conversation_id=conv_id,
            role="user",
            content="Hello",
        )
        repo.add(msg)
        session.commit()

        retrieved = repo.get(msg_id)
        assert retrieved is not None
        assert retrieved.content == "Hello"
        assert retrieved.role == "user"

    def test_message_belongs_to_conversation(self, session: Session) -> None:
        conv_id = uuid4()
        conv = ConversationModel(
            id=conv_id,
            company_id="c",
            customer_id="c",
            channel="http",
            status="active",
        )
        session.add(conv)
        session.commit()

        msg = MessageModel(
            id=uuid4(),
            conversation_id=conv_id,
            role="user",
            content="Hi",
        )
        session.add(msg)
        session.commit()

        retrieved = session.get(ConversationModel, conv_id)
        assert retrieved is not None
        assert len(retrieved.messages) == 1
        assert retrieved.messages[0].content == "Hi"


class TestBusinessEventRepository:
    def test_add_and_get(self, session: Session) -> None:
        repo = BusinessEventRepository(session=session)
        event_id = uuid4()
        event = BusinessEventModel(
            id=event_id,
            event_type="objetivo_identificado",
            source="business_brain",
            payload={"intent": "greeting"},
        )
        repo.add(event)
        session.commit()

        retrieved = repo.get(event_id)
        assert retrieved is not None
        assert retrieved.event_type == "objetivo_identificado"
        assert retrieved.payload == {"intent": "greeting"}

    def test_list_by_event_type(self, session: Session) -> None:
        repo = BusinessEventRepository(session=session)
        for _ in range(3):
            repo.add(
                BusinessEventModel(
                    id=uuid4(),
                    event_type="respuesta_generada",
                    source="business_brain",
                )
            )
        repo.add(
            BusinessEventModel(
                id=uuid4(),
                event_type="objetivo_identificado",
                source="business_brain",
            )
        )
        session.commit()

        results = repo.list(event_type="respuesta_generada")
        assert len(results) == 3

        results = repo.list(event_type="objetivo_identificado")
        assert len(results) == 1
