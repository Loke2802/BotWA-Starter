from uuid import uuid4

from app.core.conversation.context_builder import ConversationContextBuilder
from app.core.conversation.state_manager import ConversationStateManager
from app.domain.conversation.contracts import ConversationMessage


def test_build_returns_context_with_message() -> None:
    builder = ConversationContextBuilder(state_manager=ConversationStateManager())
    message = ConversationMessage(content="Hola", customer_id="c1", company_id="co1")
    state = ConversationStateManager().get_or_create(
        conversation_id=message.conversation_id, company_id="co1", customer_id="c1"
    )
    context = builder.build(message, state)
    assert context.message is message
    assert context.message.content == "Hola"


def test_build_includes_state() -> None:
    builder = ConversationContextBuilder(state_manager=ConversationStateManager())
    message = ConversationMessage(content="Hola", customer_id="c1", company_id="co1")
    state = ConversationStateManager().get_or_create(
        conversation_id=message.conversation_id, company_id="co1", customer_id="c1"
    )
    context = builder.build(message, state)
    assert context.state is state
    assert context.state.current_state == "new"


def test_build_without_repo_returns_empty_history() -> None:
    builder = ConversationContextBuilder(state_manager=ConversationStateManager())
    message = ConversationMessage(content="Hola", customer_id="c1", company_id="co1")
    state = ConversationStateManager().get_or_create(
        conversation_id=message.conversation_id, company_id="co1", customer_id="c1"
    )
    context = builder.build(message, state)
    assert context.history == []


def test_build_includes_customer_profile() -> None:
    builder = ConversationContextBuilder(state_manager=ConversationStateManager())
    message = ConversationMessage(content="Hola", customer_id="c1", company_id="co1")
    state = ConversationStateManager().get_or_create(
        conversation_id=message.conversation_id, company_id="co1", customer_id="c1"
    )
    context = builder.build(message, state)
    assert context.customer_profile == {"customer_id": "c1", "company_id": "co1"}


def test_build_includes_channel_metadata() -> None:
    metadata = {"source": "web"}
    builder = ConversationContextBuilder(state_manager=ConversationStateManager())
    message = ConversationMessage(
        content="Hola",
        customer_id="c1",
        company_id="co1",
        metadata=metadata,
    )
    state = ConversationStateManager().get_or_create(
        conversation_id=message.conversation_id, company_id="co1", customer_id="c1"
    )
    context = builder.build(message, state)
    assert context.channel_metadata == {"source": "web"}


def test_build_default_channel_is_http() -> None:
    builder = ConversationContextBuilder(state_manager=ConversationStateManager())
    message = ConversationMessage(content="Hola", customer_id="c1", company_id="co1")
    state = ConversationStateManager().get_or_create(
        conversation_id=message.conversation_id, company_id="co1", customer_id="c1"
    )
    context = builder.build(message, state)
    assert context.message.channel == "http"


def test_build_with_repo_loads_history() -> None:
    from datetime import UTC, datetime

    from app.infrastructure.database import Base
    from app.infrastructure.models.conversation import ConversationModel
    from app.infrastructure.models.message import MessageModel
    from app.infrastructure.repositories.conversation_repository import (
        ConversationRepository,
    )
    from app.infrastructure.repositories.message_repository import MessageRepository
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    conv_repo = ConversationRepository(session=session)
    msg_repo = MessageRepository(session=session)

    conv_id = uuid4()
    conv_repo.add(
        ConversationModel(
            id=conv_id,
            company_id="co1",
            customer_id="c1",
            channel="http",
            status="in_progress",
            started_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    now = datetime.now(UTC)
    msg_repo.add(
        MessageModel(
            id=uuid4(),
            conversation_id=conv_id,
            role="user",
            content="Primer mensaje",
            created_at=now,
        )
    )
    msg_repo.add(
        MessageModel(
            id=uuid4(),
            conversation_id=conv_id,
            role="assistant",
            content="Respuesta",
            created_at=now,
        )
    )
    session.commit()

    state_manager = ConversationStateManager(
        session=session, conversation_repo=conv_repo
    )
    builder = ConversationContextBuilder(
        state_manager=state_manager, message_repo=msg_repo
    )
    message = ConversationMessage(
        content="Segundo mensaje",
        customer_id="c1",
        company_id="co1",
        conversation_id=conv_id,
    )
    state = state_manager.get_or_create(
        conversation_id=conv_id, company_id="co1", customer_id="c1"
    )
    context = builder.build(message, state)
    assert len(context.history) == 2
    assert context.history[0].content == "Primer mensaje"
    assert context.history[1].content == "Respuesta"


def test_conversation_message_defaults_are_backward_compatible() -> None:
    msg = ConversationMessage(content="test", customer_id="c1", company_id="co1")
    assert msg.channel == "http"
    assert msg.metadata == {}
