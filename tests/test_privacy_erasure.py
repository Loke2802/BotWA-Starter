"""The same contract runs on FK-enforced SQLite and migrated PostgreSQL."""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.application.privacy_erasure import erase_contact
from app.infrastructure.database import Base
from app.infrastructure.models.ai_generation import AIJobModel, AIMemoryModel
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.whatsapp_message_transport import (
    InboundMessageReceiptModel,
)
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.test_transport_postgresql import seed

NOW = datetime(2026, 9, 26, tzinfo=UTC)
OLD = NOW - timedelta(days=91)


@pytest.fixture
def privacy_sessions(tmp_path) -> Generator[sessionmaker[Session]]:  # type: ignore[no-untyped-def]
    engine = create_engine(
        f"sqlite:///{tmp_path / 'privacy.db'}", connect_args={"timeout": 0.1}
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):  # type: ignore[no-untyped-def]
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False)
    engine.dispose()


def subject(sessions: sessionmaker[Session]) -> tuple[UUID, UUID, UUID]:
    with sessions() as session:
        channel = seed(session)
        contact = ContactModel(
            organization_id=channel.organization_id,
            channel_type="whatsapp",
            external_identifier_hash=str(uuid4()),
            external_identifier_ciphertext="encrypted",
            created_at=OLD,
            updated_at=OLD,
        )
        session.add(contact)
        session.flush()
        conversation = ConversationModel(
            organization_id=channel.organization_id,
            bot_id=channel.bot_id,
            company_id=str(channel.organization_id),
            customer_id="opaque",
            contact_id=contact.id,
            created_at=OLD,
            updated_at=OLD,
            started_at=OLD,
            last_message_at=OLD,
        )
        receipt = InboundMessageReceiptModel(
            channel_type="whatsapp",
            external_message_id=str(uuid4()),
            organization_id=channel.organization_id,
            bot_id=channel.bot_id,
            channel_configuration_id=channel.id,
            status="processed",
            created_at=OLD,
            updated_at=OLD,
            received_at=OLD,
            processed_at=OLD,
            payload_ciphertext="encrypted",
        )
        session.add_all([conversation, receipt])
        session.flush()
        session.add_all(
            [
                MessageModel(
                    conversation_id=conversation.id,
                    organization_id=channel.organization_id,
                    bot_id=channel.bot_id,
                    role="user",
                    content="private",
                    created_at=OLD,
                    occurred_at=OLD,
                    inbound_receipt_id=receipt.id,
                ),
                AIMemoryModel(
                    conversation_id=conversation.id,
                    organization_id=channel.organization_id,
                    bot_id=channel.bot_id,
                    ciphertext="private",
                    updated_at=OLD,
                ),
                AIJobModel(
                    receipt_id=receipt.id,
                    organization_id=channel.organization_id,
                    bot_id=channel.bot_id,
                    conversation_id=conversation.id,
                    configuration_id=channel.id,
                    status="sent",
                    sequence=1,
                    available_at=OLD,
                    created_at=OLD,
                    sent_at=OLD,
                    config_hash="test",
                ),
            ]
        )
        session.commit()
        return channel.organization_id, channel.bot_id, contact.id


def test_preview_apply_idempotency_and_isolation(
    privacy_sessions: sessionmaker[Session],
) -> None:
    scope = subject(privacy_sessions)
    other = subject(privacy_sessions)
    with privacy_sessions() as session:
        preview = erase_contact(session, *scope, now=NOW)
        assert not preview.blockers and not preview.applied
        assert preview.counts["message"] == 1
        session.commit()
    with privacy_sessions() as session:
        assert session.get(ContactModel, scope[2]) is not None
    with privacy_sessions() as session:
        result = erase_contact(
            session,
            *scope,
            now=NOW,
            apply=True,
            expected_fingerprint=preview.fingerprint,
        )
        assert result.applied and not result.blockers
        session.commit()
    with privacy_sessions() as session:
        assert session.get(ContactModel, scope[2]) is None
        assert session.get(ContactModel, other[2]) is not None
        assert len(session.scalars(select(MessageModel)).all()) == 1
    with privacy_sessions() as session:
        again = erase_contact(session, *scope, now=NOW)
        assert again.counts == {} and not again.blockers


def test_reactivation_invalidates_preview_and_request_bypasses_age(
    privacy_sessions: sessionmaker[Session],
) -> None:
    scope = subject(privacy_sessions)
    with privacy_sessions() as session:
        preview = erase_contact(session, *scope, now=NOW)
    with privacy_sessions() as session:
        session.execute(
            update(ContactModel)
            .where(ContactModel.id == scope[2])
            .values(updated_at=NOW)
        )
        session.commit()
    with privacy_sessions() as session:
        result = erase_contact(
            session,
            *scope,
            now=NOW,
            apply=True,
            expected_fingerprint=preview.fingerprint,
        )
        assert set(result.blockers) == {"stale_preview", "not_inactive_90_days"}
        assert not result.applied
    with privacy_sessions() as session:
        request = erase_contact(session, *scope, mode="request", now=NOW)
        assert not request.blockers
    with privacy_sessions() as session:
        result = erase_contact(
            session,
            *scope,
            mode="request",
            now=NOW,
            apply=True,
            expected_fingerprint=request.fingerprint,
        )
        assert result.applied
        session.commit()


@pytest.mark.parametrize(
    "status", ["pending", "running", "retry", "ready", "delivery_unknown"]
)
def test_active_ai_is_never_deleted(
    privacy_sessions: sessionmaker[Session], status: str
) -> None:
    scope = subject(privacy_sessions)
    with privacy_sessions() as session:
        session.execute(
            update(AIJobModel)
            .where(AIJobModel.bot_id == scope[1])
            .values(status=status)
        )
        session.commit()
    with privacy_sessions() as session:
        result = erase_contact(session, *scope, mode="request", now=NOW)
        assert "active_or_uncertain_ai" in result.blockers


def test_ambiguous_receipt_and_scope_fail_closed(
    privacy_sessions: sessionmaker[Session],
) -> None:
    scope = subject(privacy_sessions)
    with privacy_sessions() as session:
        original = session.scalars(select(InboundMessageReceiptModel)).one()
        session.add(
            InboundMessageReceiptModel(
                channel_type="whatsapp",
                external_message_id=str(uuid4()),
                organization_id=scope[0],
                bot_id=scope[1],
                channel_configuration_id=original.channel_configuration_id,
                status="processed",
            )
        )
        session.commit()
    with privacy_sessions() as session:
        result = erase_contact(session, *scope, now=NOW)
        assert "unattributed_receipts" in result.blockers
    with privacy_sessions() as session:
        result = erase_contact(session, uuid4(), scope[1], scope[2], now=NOW)
        assert "scope_conflict:contact" in result.blockers
        assert not result.applied


def test_row_limit_and_fresh_session(privacy_sessions: sessionmaker[Session]) -> None:
    scope = subject(privacy_sessions)
    with privacy_sessions() as session:
        result = erase_contact(session, *scope, now=NOW, max_rows=1)
        assert "row_limit" in result.blockers
        with pytest.raises(ValueError, match="fresh session"):
            erase_contact(session, *scope)
    with privacy_sessions() as session, pytest.raises(ValueError, match="fingerprint"):
        erase_contact(session, *scope, apply=True)


def test_maintenance_lock_excludes_writers_and_other_erasers(
    privacy_sessions: sessionmaker[Session],
) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    scope = subject(privacy_sessions)
    with privacy_sessions() as locked:
        result = erase_contact(locked, *scope, now=NOW)
        assert not result.blockers
        with privacy_sessions() as writer:
            if writer.get_bind().dialect.name == "postgresql":
                writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
            with pytest.raises(OperationalError):
                writer.execute(
                    update(ContactModel)
                    .where(ContactModel.id == scope[2])
                    .values(updated_at=NOW)
                )
            writer.rollback()
        with privacy_sessions() as contender, pytest.raises(OperationalError):
            erase_contact(contender, *scope, now=NOW)
    with privacy_sessions() as writer:
        writer.execute(
            update(ContactModel)
            .where(ContactModel.id == scope[2])
            .values(updated_at=NOW)
        )
        writer.commit()


def test_shared_contact_and_reverse_transport_block(
    privacy_sessions: sessionmaker[Session],
) -> None:
    from app.infrastructure.models.bot import BotModel

    scope = subject(privacy_sessions)
    with privacy_sessions() as session:
        bot = BotModel(
            organization_id=scope[0], name="Another", slug=str(uuid4()), status="active"
        )
        session.add(bot)
        session.flush()
        conversation = ConversationModel(
            organization_id=scope[0],
            bot_id=bot.id,
            company_id=str(scope[0]),
            customer_id="opaque",
            contact_id=scope[2],
        )
        session.add(conversation)
        session.commit()
    with privacy_sessions() as session:
        result = erase_contact(session, *scope, now=NOW, mode="request")
        assert "scope_conflict:conversation" in result.blockers


def test_history_handoff_transport_and_checkpoints_are_removed(
    privacy_sessions: sessionmaker[Session],
) -> None:
    from app.infrastructure.models.ai_generation import (
        AIAttemptModel,
        AIResponseCheckpointModel,
    )
    from app.infrastructure.models.conversation_state_history import (
        ConversationStateHistoryModel,
    )
    from app.infrastructure.models.human_handoff import (
        HandoffEventModel,
        HandoffSessionModel,
    )
    from app.infrastructure.models.whatsapp_message_transport import (
        OutboundMessageAttemptModel,
    )

    scope = subject(privacy_sessions)
    with privacy_sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        contact = session.get(ContactModel, scope[2])
        assert contact
        handoff = HandoffSessionModel(
            conversation_id=job.conversation_id,
            organization_id=scope[0],
            bot_id=scope[1],
            status="resolved",
            last_activity_at=OLD,
            created_at=OLD,
            updated_at=OLD,
        )
        attempt = OutboundMessageAttemptModel(
            organization_id=scope[0],
            bot_id=scope[1],
            channel_configuration_id=job.configuration_id,
            inbound_receipt_id=job.receipt_id,
            external_recipient_hash=contact.external_identifier_hash,
            external_recipient_ciphertext="encrypted",
            message_ciphertext="encrypted",
            status="sent",
            created_at=OLD,
            updated_at=OLD,
            sent_at=OLD,
        )
        session.add_all([handoff, attempt])
        session.flush()
        job.outbound_id = attempt.id
        session.add_all(
            [
                HandoffEventModel(
                    handoff_session_id=handoff.id,
                    organization_id=scope[0],
                    event_type="resolved",
                    created_at=OLD,
                ),
                ConversationStateHistoryModel(
                    conversation_id=job.conversation_id,
                    from_state="active",
                    to_state="closed",
                    created_at=OLD,
                ),
                AIAttemptModel(
                    job_id=job.id,
                    stage="discovery",
                    model="fake",
                    prompt_version="1",
                    started_at=OLD,
                ),
                AIResponseCheckpointModel(
                    job_id=job.id, memory_revision=0, ciphertext="encrypted"
                ),
            ]
        )
        session.commit()
    with privacy_sessions() as session:
        preview = erase_contact(session, *scope, now=NOW)
        assert not preview.blockers
        assert preview.counts["handoff_event"] == 1
        assert preview.counts["ai_response_checkpoint"] == 1
    with privacy_sessions() as session:
        result = erase_contact(
            session,
            *scope,
            now=NOW,
            apply=True,
            expected_fingerprint=preview.fingerprint,
        )
        assert result.applied
        session.commit()
    with privacy_sessions() as session:
        for name in preview.counts:
            assert not session.execute(select(Base.metadata.tables[name])).first()


@pytest.mark.parametrize(
    "legacy", ["conversation", "knowledge_query_log", "automation_execution"]
)
def test_legacy_unattributed_data_blocks(
    privacy_sessions: sessionmaker[Session], legacy: str
) -> None:
    from app.infrastructure.models.automation_execution import AutomationExecutionModel
    from app.infrastructure.models.knowledge_query_log import KnowledgeQueryLogModel

    scope = subject(privacy_sessions)
    with privacy_sessions() as session:
        if legacy == "conversation":
            session.add(ConversationModel(company_id="legacy", customer_id="unknown"))
        elif legacy == "knowledge_query_log":
            session.add(
                KnowledgeQueryLogModel(query_text="unknown subject", intent="test")
            )
        else:
            session.add(AutomationExecutionModel(execution_id=uuid4(), plan_id=uuid4()))
        session.commit()
    with privacy_sessions() as session:
        result = erase_contact(session, *scope, now=NOW, mode="request")
        assert result.blockers and not result.applied


def test_reverse_link_and_rollback(privacy_sessions: sessionmaker[Session]) -> None:
    scope = subject(privacy_sessions)
    other = subject(privacy_sessions)
    with privacy_sessions() as session:
        own = session.scalars(
            select(AIJobModel).where(AIJobModel.bot_id == scope[1])
        ).one()
        alien = session.scalars(
            select(MessageModel).where(MessageModel.bot_id == other[1])
        ).one()
        alien.inbound_receipt_id = own.receipt_id
        session.commit()
    with privacy_sessions() as session:
        preview = erase_contact(session, *scope, now=NOW)
        assert "shared_transport:message" in preview.blockers
    with privacy_sessions() as session:
        alien = session.scalars(
            select(MessageModel).where(MessageModel.bot_id == other[1])
        ).one()
        alien.inbound_receipt_id = None
        session.commit()
    with privacy_sessions() as session:
        preview = erase_contact(session, *scope, now=NOW)
        assert not preview.blockers
    with privacy_sessions() as session:
        result = erase_contact(
            session,
            *scope,
            now=NOW,
            apply=True,
            expected_fingerprint=preview.fingerprint,
        )
        assert result.applied
        session.rollback()
    with privacy_sessions() as session:
        assert session.get(ContactModel, scope[2]) is not None


@pytest.mark.parametrize("days,blocked", [(89, True), (90, False)])
def test_activity_boundary(
    privacy_sessions: sessionmaker[Session], days: int, blocked: bool
) -> None:
    scope = subject(privacy_sessions)
    with privacy_sessions() as session:
        session.execute(
            update(MessageModel)
            .where(MessageModel.bot_id == scope[1])
            .values(occurred_at=NOW - timedelta(days=days))
        )
        session.commit()
    with privacy_sessions() as session:
        preview = erase_contact(session, *scope, now=NOW)
        assert ("not_inactive_90_days" in preview.blockers) is blocked


def test_other_tenant_legacy_event_blocks_without_erasing_it(
    privacy_sessions: sessionmaker[Session],
) -> None:
    from app.infrastructure.models.integration_event import IntegrationEventModel

    scope = subject(privacy_sessions)
    other = subject(privacy_sessions)
    with privacy_sessions() as session:
        session.add(
            IntegrationEventModel(
                event_type="legacy",
                capability="test",
                provider_id="fake",
                tenant_id=str(other[0]),
                request_id=uuid4(),
                success=True,
            )
        )
        session.commit()
    with privacy_sessions() as session:
        preview = erase_contact(session, *scope, now=NOW, mode="request")
        assert "unattributed_store:integration_event" in preview.blockers
    with privacy_sessions() as session:
        result = erase_contact(
            session,
            *scope,
            now=NOW,
            mode="request",
            apply=True,
            expected_fingerprint=preview.fingerprint,
        )
        assert not result.applied
        session.commit()
    with privacy_sessions() as session:
        assert session.get(ContactModel, scope[2]) is not None
        assert session.get(ContactModel, other[2]) is not None
        assert session.scalars(select(IntegrationEventModel)).one().tenant_id == str(
            other[0]
        )


def test_internal_timestamp_is_a_separate_safety_block(
    privacy_sessions: sessionmaker[Session],
) -> None:
    scope = subject(privacy_sessions)
    with privacy_sessions() as session:
        session.execute(
            update(AIMemoryModel)
            .where(AIMemoryModel.bot_id == scope[1])
            .values(updated_at=NOW)
        )
        session.commit()
    with privacy_sessions() as session:
        preview = erase_contact(session, *scope, now=NOW)
        assert preview.blockers == ("recent_related_change",)
