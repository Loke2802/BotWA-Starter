from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_conversation_service
from app.api.whatsapp_configuration_dependencies import (
    get_whatsapp_secret_cipher,
)
from app.application.automation_management.service import ManagedAutomationService
from app.application.channel.conversation_handler import (
    ChannelConversationHandler,
)
from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.service import ContactResolutionService
from app.application.conversation_management.managed_handler import (
    ManagedChannelConversationHandler,
)
from app.application.conversation_management.service import (
    ConversationManagementService,
)
from app.application.human_handoff.service import HumanHandoffService
from app.application.knowledge_management.provider import BotKnowledgeProvider
from app.application.whatsapp_configuration.resolver import (
    WhatsAppChannelResolver,
)
from app.application.whatsapp_live.client import WhatsAppCloudApiClient
from app.application.whatsapp_live.processor import WhatsAppLiveMessageProcessor
from app.application.whatsapp_live.sender import WhatsAppChannelMessageSender
from app.channels.whatsapp.live_mapper import WhatsAppInboundMessageMapper
from app.core.conversation.service import ConversationService
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.infrastructure.database import get_session
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.contact_repository import (
    SqlAlchemyContactRepository,
)
from app.infrastructure.repositories.conversation_management_repository import (
    SqlAlchemyConversationManagementRepository,
    SqlAlchemyConversationMessageManagementRepository,
)
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.infrastructure.repositories.knowledge_entry_repository import (
    SqlAlchemyKnowledgeEntryRepository,
)
from app.infrastructure.repositories.managed_automation_repository import (
    ManagedAutomationRepository,
)
from app.infrastructure.repositories.whatsapp_configuration_repository import (
    SqlAlchemyWhatsAppConfigurationRepository,
)
from app.infrastructure.repositories.whatsapp_message_transport_repository import (
    SqlAlchemyInboundMessageReceiptRepository,
    SqlAlchemyOutboundMessageAttemptRepository,
)
from app.infrastructure.settings import Settings, get_settings
from app.infrastructure.whatsapp.fake_client import FakeWhatsAppCloudApiClient
from app.infrastructure.whatsapp.meta_client import MetaWhatsAppCloudApiClient
from app.security.secret_cipher import SecretCipher


def get_whatsapp_cloud_api_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> WhatsAppCloudApiClient:
    if settings.whatsapp_live_client_mode == "fake":
        return FakeWhatsAppCloudApiClient()
    if settings.whatsapp_live_client_mode == "meta":
        return MetaWhatsAppCloudApiClient(
            api_version=settings.whatsapp_api_version,
            timeout_seconds=settings.whatsapp_meta_timeout_seconds,
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="WhatsApp live messaging client is disabled",
    )


def get_whatsapp_live_message_processor(
    session: Annotated[Session, Depends(get_session)],
    conversation_service: Annotated[
        ConversationService,
        Depends(get_conversation_service),
    ],
    secret_cipher: Annotated[
        SecretCipher,
        Depends(get_whatsapp_secret_cipher),
    ],
    client: Annotated[
        WhatsAppCloudApiClient,
        Depends(get_whatsapp_cloud_api_client),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WhatsAppLiveMessageProcessor:
    configuration_repository = SqlAlchemyWhatsAppConfigurationRepository(session)
    audit_writer = SqlAlchemyAuditRepository(session)
    management = ConversationManagementService(
        conversations=SqlAlchemyConversationManagementRepository(session),
        messages=SqlAlchemyConversationMessageManagementRepository(
            session, audit_writer
        ),
        bot_repository=BotRepository(session),
        cipher=secret_cipher,
        session=session,
        audit_writer=audit_writer,
    )
    handoff = HumanHandoffService(
        HumanHandoffRepository(session), session, audit_writer
    )
    contacts = ContactResolutionService(
        SqlAlchemyContactRepository(session),
        ContactIdentityHasher(
            settings.contact_identity_hmac_key,
            ContactIdentityNormalizer(),
        ),
        secret_cipher,
        session,
    )
    handler = ManagedChannelConversationHandler(
        ChannelConversationHandler(
            conversation_service,
            BotKnowledgeProvider(SqlAlchemyKnowledgeEntryRepository(session)),
            persist_core_messages=False,
        ),
        management,
        handoff,
        contacts,
        ManagedAutomationService(
            ManagedAutomationRepository(session),
            session,
            audit_writer,
            handoff=handoff,
        ),
    )
    sender = WhatsAppChannelMessageSender(
        configuration_repository,
        secret_cipher,
        client,
        max_text_chars=settings.whatsapp_outbound_max_text_chars,
    )
    return WhatsAppLiveMessageProcessor(
        configuration_repository=configuration_repository,
        receipt_repository=SqlAlchemyInboundMessageReceiptRepository(session),
        outbound_repository=SqlAlchemyOutboundMessageAttemptRepository(session),
        resolver=WhatsAppChannelResolver(configuration_repository),
        mapper=WhatsAppInboundMessageMapper(),
        handler=handler,
        sender=sender,
        secret_cipher=secret_cipher,
        session=session,
        max_text_chars=settings.whatsapp_outbound_max_text_chars,
        max_attempts=settings.whatsapp_outbound_max_attempts,
        retry_base_seconds=settings.whatsapp_outbound_retry_base_seconds,
        retry_max_seconds=settings.whatsapp_outbound_retry_max_seconds,
        conversation_management=management,
    )
