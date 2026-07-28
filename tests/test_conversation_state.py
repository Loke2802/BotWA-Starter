from uuid import uuid4

import pytest
from app.core.conversation.state_manager import ConversationStateManager


def test_initial_state_is_new() -> None:
    manager = ConversationStateManager()
    state = manager.get_or_create(
        conversation_id=uuid4(),
        company_id="c",
        customer_id="c",
    )
    assert state.current_state == "new"


def test_get_or_create_returns_same_for_existing() -> None:
    manager = ConversationStateManager()
    conv_id = uuid4()
    state1 = manager.get_or_create(
        conversation_id=conv_id, company_id="c", customer_id="c"
    )
    state2 = manager.get_or_create(
        conversation_id=conv_id, company_id="c", customer_id="c"
    )
    assert state1.current_state == state2.current_state


def test_transition_new_to_in_progress() -> None:
    manager = ConversationStateManager()
    conv_id = uuid4()
    manager.get_or_create(conv_id, "c", "c")
    state = manager.transition(conv_id, "in_progress")
    assert state.current_state == "in_progress"


def test_transition_in_progress_to_awaiting_brain() -> None:
    manager = ConversationStateManager()
    conv_id = uuid4()
    manager.get_or_create(conv_id, "c", "c")
    manager.transition(conv_id, "in_progress")
    state = manager.transition(conv_id, "awaiting_brain")
    assert state.current_state == "awaiting_brain"


def test_transition_awaiting_brain_to_in_progress() -> None:
    manager = ConversationStateManager()
    conv_id = uuid4()
    manager.get_or_create(conv_id, "c", "c")
    manager.transition(conv_id, "in_progress")
    manager.transition(conv_id, "awaiting_brain")
    state = manager.transition(conv_id, "in_progress")
    assert state.current_state == "in_progress"


def test_full_pipeline_sequence() -> None:
    manager = ConversationStateManager()
    conv_id = uuid4()
    manager.get_or_create(conv_id, "c", "c")
    assert manager.transition(conv_id, "in_progress").current_state == "in_progress"
    assert (
        manager.transition(conv_id, "awaiting_brain").current_state == "awaiting_brain"
    )
    assert manager.transition(conv_id, "in_progress").current_state == "in_progress"


def test_transition_from_terminal_raises() -> None:
    manager = ConversationStateManager()
    conv_id = uuid4()
    manager.get_or_create(conv_id, "c", "c")
    manager.transition(conv_id, "in_progress")
    manager.transition(conv_id, "completed")
    with pytest.raises(ValueError, match="Transition not allowed"):
        manager.transition(conv_id, "in_progress")


def test_transition_invalid_raises() -> None:
    manager = ConversationStateManager()
    conv_id = uuid4()
    manager.get_or_create(conv_id, "c", "c")
    with pytest.raises(ValueError, match="Transition not allowed"):
        manager.transition(conv_id, "completed")


def test_can_transition_valid() -> None:
    manager = ConversationStateManager()
    assert manager.can_transition("new", "in_progress") is True
    assert manager.can_transition("in_progress", "awaiting_brain") is True
    assert manager.can_transition("awaiting_brain", "in_progress") is True


def test_can_transition_invalid() -> None:
    manager = ConversationStateManager()
    assert manager.can_transition("new", "completed") is False
    assert manager.can_transition("completed", "in_progress") is False
    assert manager.can_transition("in_progress", "new") is False


def test_is_terminal() -> None:
    assert ConversationStateManager.is_terminal("completed") is True
    assert ConversationStateManager.is_terminal("cancelled") is True
    assert ConversationStateManager.is_terminal("escalated") is True
    assert ConversationStateManager.is_terminal("in_progress") is False
    assert ConversationStateManager.is_terminal("new") is False


def test_get_or_create_with_db_persists_conversation() -> None:
    from app.infrastructure.database import Base
    from app.infrastructure.repositories.conversation_repository import (
        ConversationRepository,
    )
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = ConversationRepository(session=session)
    manager = ConversationStateManager(session=session, conversation_repo=repo)

    conv_id = uuid4()
    manager.get_or_create(conv_id, "c", "c")
    session.commit()

    conv = repo.get(conv_id)
    assert conv is not None
    assert conv.status == "new"


def test_transition_with_db_persists() -> None:
    from app.infrastructure.database import Base
    from app.infrastructure.repositories.conversation_repository import (
        ConversationRepository,
    )
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = ConversationRepository(session=session)
    manager = ConversationStateManager(session=session, conversation_repo=repo)

    conv_id = uuid4()
    manager.get_or_create(conv_id, "c", "c")
    manager.transition(conv_id, "in_progress")
    session.commit()

    conv = repo.get(conv_id)
    assert conv is not None
    assert conv.status == "in_progress"


def test_transition_with_db_creates_history() -> None:
    from app.infrastructure.database import Base
    from app.infrastructure.models.conversation_state_history import (
        ConversationStateHistoryModel,
    )
    from app.infrastructure.repositories.conversation_repository import (
        ConversationRepository,
    )
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = ConversationRepository(session=session)
    manager = ConversationStateManager(session=session, conversation_repo=repo)

    conv_id = uuid4()
    manager.get_or_create(conv_id, "c", "c")
    manager.transition(conv_id, "in_progress")
    session.commit()

    history = (
        session.query(ConversationStateHistoryModel)
        .filter_by(conversation_id=conv_id)
        .all()
    )
    assert len(history) == 1
    assert history[0].from_state == "new"
    assert history[0].to_state == "in_progress"


def test_terminal_state_blocks_processing() -> None:
    manager = ConversationStateManager()
    conv_id = uuid4()
    manager.get_or_create(conv_id, "c", "c")
    manager.transition(conv_id, "in_progress")
    manager.transition(conv_id, "completed")
    assert ConversationStateManager.is_terminal("completed") is True
