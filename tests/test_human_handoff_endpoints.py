import base64
from collections import deque
from collections.abc import Generator
from typing import cast
from uuid import UUID, uuid4

import pytest
from app.api.dependencies import require_authenticated_user
from app.api.human_handoff_dependencies import get_human_handoff_service
from app.api.whatsapp_live_dependencies import get_whatsapp_live_message_processor
from app.application.conversation_management.service import (
    ConversationManagementService,
)
from app.application.human_handoff.service import HumanHandoffService
from app.application.whatsapp_configuration.resolver import WhatsAppChannelResolver
from app.application.whatsapp_live.processor import WhatsAppLiveMessageProcessor
from app.application.whatsapp_live.sender import WhatsAppChannelMessageSender
from app.channels.whatsapp.live_mapper import WhatsAppInboundMessageMapper
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel,
)
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.conversation_management_repository import (
    SqlAlchemyConversationManagementRepository,
    SqlAlchemyConversationMessageManagementRepository,
)
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.infrastructure.repositories.whatsapp_configuration_repository import (
    SqlAlchemyWhatsAppConfigurationRepository,
)
from app.infrastructure.repositories.whatsapp_message_transport_repository import (
    SqlAlchemyInboundMessageReceiptRepository,
    SqlAlchemyOutboundMessageAttemptRepository,
)
from app.infrastructure.whatsapp.fake_client import FakeWhatsAppCloudApiClient
from app.main import create_app
from app.security.secret_cipher import EnvironmentSecretCipher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def runtime() -> (
    Generator[
        tuple[TestClient, Session, User, User, UUID, UUID, FakeWhatsAppCloudApiClient]
    ]
):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    (
        organization_id,
        bot_id,
        agent_id,
        operator_id,
        conversation_id,
        configuration_id,
    ) = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    cipher = EnvironmentSecretCipher(
        base64.urlsafe_b64encode(b"h" * 32).decode("ascii")
    )
    session.add_all(
        (
            OrganizationModel(
                id=organization_id,
                name="Org",
                slug=str(organization_id)[:12],
                status="active",
            ),
            BotModel(
                id=bot_id,
                organization_id=organization_id,
                name="Bot",
                slug="bot",
                status="active",
            ),
            UserModel(
                id=agent_id,
                organization_id=organization_id,
                email="agent@example.com",
                password_hash="x",
                role="organization_owner",
                status="active",
            ),
            UserModel(
                id=operator_id,
                organization_id=organization_id,
                email="operator@example.com",
                password_hash="x",
                role="operator",
                status="active",
            ),
            ConversationModel(
                id=conversation_id,
                company_id=str(organization_id),
                customer_id="51999999999",
                organization_id=organization_id,
                bot_id=bot_id,
                channel_configuration_id=configuration_id,
                external_customer_id="51999999999",
                channel="whatsapp",
                management_status="open",
                status="new",
            ),
            WhatsAppChannelConfigurationModel(
                id=configuration_id,
                organization_id=organization_id,
                bot_id=bot_id,
                display_name="Support",
                phone_number_id="123456789",
                whatsapp_business_account_id="waba-123456789",
                public_webhook_id=uuid4(),
                status="active",
                webhook_enabled=True,
                verify_token_ciphertext=cipher.encrypt("verify-token"),
                access_token_ciphertext=cipher.encrypt("access-token"),
                app_secret_ciphertext=cipher.encrypt("app-secret"),
                created_by_user_id=agent_id,
            ),
        )
    )
    session.commit()
    actor = User(
        id=agent_id,
        organization_id=organization_id,
        email="agent@example.com",
        role="organization_owner",
    )
    operator = User(
        id=operator_id,
        organization_id=organization_id,
        email="operator@example.com",
        role="operator",
    )
    audit_writer = SqlAlchemyAuditRepository(session)
    service = HumanHandoffService(
        HumanHandoffRepository(session), session, audit_writer
    )
    service.request(organization_id, conversation_id, actor, None)
    service.claim(organization_id, conversation_id, actor)
    configurations = SqlAlchemyWhatsAppConfigurationRepository(session)
    fake_client = FakeWhatsAppCloudApiClient()
    management = ConversationManagementService(
        conversations=SqlAlchemyConversationManagementRepository(session),
        messages=SqlAlchemyConversationMessageManagementRepository(
            session, audit_writer
        ),
        bot_repository=None,  # type: ignore[arg-type]
        cipher=cipher,
        session=session,
        audit_writer=audit_writer,
    )
    processor = WhatsAppLiveMessageProcessor(
        configuration_repository=configurations,
        receipt_repository=SqlAlchemyInboundMessageReceiptRepository(session),
        outbound_repository=SqlAlchemyOutboundMessageAttemptRepository(session),
        resolver=WhatsAppChannelResolver(configurations),
        mapper=WhatsAppInboundMessageMapper(),
        handler=None,  # type: ignore[arg-type]
        sender=WhatsAppChannelMessageSender(
            configurations, cipher, fake_client, max_text_chars=4096
        ),
        secret_cipher=cipher,
        session=session,
        max_text_chars=4096,
        max_attempts=3,
        retry_base_seconds=1,
        retry_max_seconds=60,
        conversation_management=management,
    )
    app = create_app()
    app.dependency_overrides[get_human_handoff_service] = lambda: service
    app.dependency_overrides[get_whatsapp_live_message_processor] = lambda: processor
    app.dependency_overrides[require_authenticated_user] = lambda: actor
    try:
        with TestClient(app) as api_client:
            yield (
                api_client,
                session,
                actor,
                operator,
                organization_id,
                conversation_id,
                fake_client,
            )
    finally:
        session.close()
        app.dependency_overrides.clear()


def test_assigned_active_agent_can_send_human_reply(
    runtime: tuple[
        TestClient, Session, User, User, UUID, UUID, FakeWhatsAppCloudApiClient
    ],
) -> None:
    client, _, actor, _, organization_id, conversation_id, sender = runtime

    response = client.post(
        f"/organizations/{organization_id}/conversations/{conversation_id}/handoff/messages",
        json={"text": "Hola, soy tu agente.", "idempotency_key": "human-reply-001"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert len(sender.calls) == 1


def test_unassigned_operator_cannot_send_human_reply(
    runtime: tuple[
        TestClient, Session, User, User, UUID, UUID, FakeWhatsAppCloudApiClient
    ],
) -> None:
    client, _, _, operator, organization_id, conversation_id, _ = runtime
    cast(FastAPI, client.app).dependency_overrides[
        require_authenticated_user
    ] = lambda: operator

    response = client.post(
        f"/organizations/{organization_id}/conversations/{conversation_id}/handoff/messages",
        json={"text": "Hola", "idempotency_key": "human-reply-002"},
    )

    assert response.status_code == 403


def test_waiting_human_handoff_cannot_send_human_reply(
    runtime: tuple[
        TestClient, Session, User, User, UUID, UUID, FakeWhatsAppCloudApiClient
    ],
) -> None:
    client, _, _, _, organization_id, conversation_id, _ = runtime
    release = client.post(
        f"/organizations/{organization_id}/conversations/{conversation_id}/handoff/release"
    )
    response = client.post(
        f"/organizations/{organization_id}/conversations/{conversation_id}/handoff/messages",
        json={"text": "Hola", "idempotency_key": "human-reply-003"},
    )

    assert release.status_code == 200
    assert response.status_code == 409


def test_repeated_idempotency_key_does_not_send_twice(
    runtime: tuple[
        TestClient, Session, User, User, UUID, UUID, FakeWhatsAppCloudApiClient
    ],
) -> None:
    client, _, _, _, organization_id, conversation_id, sender = runtime
    path = (
        f"/organizations/{organization_id}/conversations/"
        f"{conversation_id}/handoff/messages"
    )
    payload = {"text": "Hola", "idempotency_key": "human-reply-004"}

    first = client.post(path, json=payload)
    repeated = client.post(path, json=payload)

    assert first.status_code == 200
    assert repeated.status_code == 200
    assert first.json()["attempt_id"] == repeated.json()["attempt_id"]
    assert len(sender.calls) == 1


def test_human_reply_persists_author_user_id(
    runtime: tuple[
        TestClient, Session, User, User, UUID, UUID, FakeWhatsAppCloudApiClient
    ],
) -> None:
    client, session, actor, _, organization_id, conversation_id, _ = runtime
    client.post(
        f"/organizations/{organization_id}/conversations/{conversation_id}/handoff/messages",
        json={"text": "Respuesta administrativa", "idempotency_key": "human-reply-005"},
    )

    message = session.scalars(select(MessageModel)).one()

    assert message.author_user_id == actor.id


def test_administrative_outbound_message_is_encrypted_at_rest(
    runtime: tuple[
        TestClient, Session, User, User, UUID, UUID, FakeWhatsAppCloudApiClient
    ],
) -> None:
    client, session, _, _, organization_id, conversation_id, _ = runtime
    plaintext = "Respuesta administrativa secreta"
    client.post(
        f"/organizations/{organization_id}/conversations/{conversation_id}/handoff/messages",
        json={"text": plaintext, "idempotency_key": "human-reply-006"},
    )

    message = session.scalars(select(MessageModel)).one()

    assert message.text_ciphertext is not None
    assert message.text_ciphertext != plaintext


def test_administrative_outbound_plaintext_is_not_persisted(
    runtime: tuple[
        TestClient, Session, User, User, UUID, UUID, FakeWhatsAppCloudApiClient
    ],
) -> None:
    client, session, _, _, organization_id, conversation_id, _ = runtime
    plaintext = "Texto administrativo confidencial"
    client.post(
        f"/organizations/{organization_id}/conversations/{conversation_id}/handoff/messages",
        json={"text": plaintext, "idempotency_key": "human-reply-007"},
    )

    message = session.scalars(select(MessageModel)).one()
    attempt = session.scalars(select(OutboundMessageAttemptModel)).one()

    assert plaintext not in (message.content, message.text_ciphertext or "")
    assert plaintext not in attempt.message_ciphertext
    assert plaintext not in attempt.external_recipient_ciphertext


def test_human_reply_creates_one_linked_outbound_message_attempt(
    runtime: tuple[
        TestClient, Session, User, User, UUID, UUID, FakeWhatsAppCloudApiClient
    ],
) -> None:
    client, session, _, _, organization_id, conversation_id, _ = runtime
    response = client.post(
        f"/organizations/{organization_id}/conversations/{conversation_id}/handoff/messages",
        json={"text": "Respuesta", "idempotency_key": "human-reply-008"},
    )

    message = session.scalars(select(MessageModel)).one()
    attempts = list(session.scalars(select(OutboundMessageAttemptModel)))

    assert len(attempts) == 1
    assert message.outbound_attempt_id == attempts[0].id
    assert response.json()["attempt_id"] == str(attempts[0].id)


def test_sender_timeout_returns_controlled_response_and_schedules_retry(
    runtime: tuple[
        TestClient, Session, User, User, UUID, UUID, FakeWhatsAppCloudApiClient
    ],
) -> None:
    client, session, _, _, organization_id, conversation_id, sender = runtime
    plaintext = "timeout plaintext"
    sender._outcomes = deque(("timeout",))

    response = client.post(
        f"/organizations/{organization_id}/conversations/{conversation_id}/handoff/messages",
        json={"text": plaintext, "idempotency_key": "human-reply-009"},
    )

    attempt = session.scalars(select(OutboundMessageAttemptModel)).one()
    messages = list(session.scalars(select(MessageModel)))
    response_text = response.text
    assert response.status_code == 503
    assert response.json() == {"detail": "message delivery could not be completed"}
    assert attempt.status == "pending"
    assert attempt.last_error_code == "TIMEOUT"
    assert attempt.next_attempt_at is not None
    assert len(messages) == 1
    assert len(sender.calls) == 1
    assert all(
        secret not in response_text
        for secret in (
            plaintext,
            "access-token",
            "51999999999",
            attempt.message_ciphertext,
        )
    )


def test_sender_http_400_returns_controlled_response_and_persists_failure(
    runtime: tuple[
        TestClient, Session, User, User, UUID, UUID, FakeWhatsAppCloudApiClient
    ],
) -> None:
    client, session, _, _, organization_id, conversation_id, sender = runtime
    plaintext = "bad request plaintext"
    sender._outcomes = deque(("400",))

    response = client.post(
        f"/organizations/{organization_id}/conversations/{conversation_id}/handoff/messages",
        json={"text": plaintext, "idempotency_key": "human-reply-010"},
    )

    attempt = session.scalars(select(OutboundMessageAttemptModel)).one()
    messages = list(session.scalars(select(MessageModel)))
    response_text = response.text
    assert response.status_code == 400
    assert response.json() == {"detail": "message delivery could not be completed"}
    assert attempt.status == "failed"
    assert attempt.last_error_code == "INVALID_REQUEST"
    assert attempt.next_attempt_at is None
    assert len(messages) == 1
    assert len(sender.calls) == 1
    assert all(
        secret not in response_text
        for secret in (
            plaintext,
            "access-token",
            "51999999999",
            attempt.message_ciphertext,
        )
    )


def test_sender_http_429_returns_controlled_response_and_schedules_retry(
    runtime: tuple[
        TestClient, Session, User, User, UUID, UUID, FakeWhatsAppCloudApiClient
    ],
) -> None:
    client, session, _, _, organization_id, conversation_id, sender = runtime
    plaintext = "rate limited plaintext"
    sender._outcomes = deque(("429",))

    response = client.post(
        f"/organizations/{organization_id}/conversations/{conversation_id}/handoff/messages",
        json={"text": plaintext, "idempotency_key": "human-reply-011"},
    )

    attempt = session.scalars(select(OutboundMessageAttemptModel)).one()
    messages = list(session.scalars(select(MessageModel)))
    response_text = response.text
    assert response.status_code == 429
    assert response.json() == {"detail": "message delivery could not be completed"}
    assert attempt.status == "pending"
    assert attempt.last_error_code == "RATE_LIMITED"
    assert attempt.next_attempt_at is not None
    assert len(messages) == 1
    assert len(sender.calls) == 1
    assert all(
        secret not in response_text
        for secret in (
            plaintext,
            "access-token",
            "51999999999",
            attempt.message_ciphertext,
        )
    )


def test_sender_http_500_returns_controlled_response_and_schedules_retry(
    runtime: tuple[
        TestClient, Session, User, User, UUID, UUID, FakeWhatsAppCloudApiClient
    ],
) -> None:
    client, session, _, _, organization_id, conversation_id, sender = runtime
    plaintext = "provider unavailable plaintext"
    sender._outcomes = deque(("500",))

    response = client.post(
        f"/organizations/{organization_id}/conversations/{conversation_id}/handoff/messages",
        json={"text": plaintext, "idempotency_key": "human-reply-012"},
    )

    attempt = session.scalars(select(OutboundMessageAttemptModel)).one()
    messages = list(session.scalars(select(MessageModel)))
    response_text = response.text
    assert response.status_code == 503
    assert response.json() == {"detail": "message delivery could not be completed"}
    assert attempt.status == "pending"
    assert attempt.last_error_code == "PROVIDER_UNAVAILABLE"
    assert attempt.next_attempt_at is not None
    assert len(messages) == 1
    assert len(sender.calls) == 1
    assert all(
        secret not in response_text
        for secret in (
            plaintext,
            "access-token",
            "51999999999",
            attempt.message_ciphertext,
        )
    )
