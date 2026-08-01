import hashlib
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import structlog
from sqlalchemy.orm import Session

from app.application.channel.messaging import (
    ChannelMessageHandler,
    ChannelMessageSender,
)
from app.application.channel.resolver import ChannelResolutionError
from app.application.channel.text_splitter import split_outbound_message
from app.application.conversation_management.service import (
    ConversationManagementService,
)
from app.application.whatsapp_configuration.repository import (
    WhatsAppConfigurationRepository,
)
from app.application.whatsapp_configuration.resolver import (
    WhatsAppChannelResolver,
)
from app.application.whatsapp_live.repository import (
    InboundMessageReceiptRepository,
    OutboundMessageAttemptRepository,
)
from app.application.whatsapp_live.sender import WhatsAppChannelDeliveryError
from app.channels.whatsapp.live_mapper import WhatsAppInboundMessageMapper
from app.domain.channel.contracts import (
    MessageProcessingResult,
    OutboundChannelMessage,
    ResolvedChannelContext,
)
from app.domain.whatsapp_live.contracts import (
    WhatsAppParsedWebhook,
    WhatsAppStatusEvent,
)
from app.infrastructure.models.whatsapp_message_transport import (
    InboundMessageReceiptModel,
    OutboundMessageAttemptModel,
)
from app.security.secret_cipher import SecretCipher

logger = structlog.get_logger(__name__)


class WhatsAppRuntimeRoutingError(ValueError):
    pass


class WhatsAppLiveMessageProcessor:
    def __init__(
        self,
        *,
        configuration_repository: WhatsAppConfigurationRepository,
        receipt_repository: InboundMessageReceiptRepository,
        outbound_repository: OutboundMessageAttemptRepository,
        resolver: WhatsAppChannelResolver,
        mapper: WhatsAppInboundMessageMapper,
        handler: ChannelMessageHandler,
        sender: ChannelMessageSender,
        secret_cipher: SecretCipher,
        session: Session,
        max_text_chars: int,
        max_attempts: int,
        retry_base_seconds: float,
        retry_max_seconds: float,
        conversation_management: ConversationManagementService | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._configuration_repository = configuration_repository
        self._receipt_repository = receipt_repository
        self._outbound_repository = outbound_repository
        self._resolver = resolver
        self._mapper = mapper
        self._handler = handler
        self._sender = sender
        self._secret_cipher = secret_cipher
        self._session = session
        self._max_text_chars = max_text_chars
        self._max_attempts = max_attempts
        self._retry_base_seconds = retry_base_seconds
        self._retry_max_seconds = retry_max_seconds
        self._conversation_management = conversation_management
        self._now = now or (lambda: datetime.now(UTC))

    async def process(
        self,
        payload: WhatsAppParsedWebhook,
        *,
        public_webhook_id: UUID,
        correlation_id: UUID,
    ) -> tuple[MessageProcessingResult, ...]:
        configuration = self._configuration_repository.get_active_by_public_webhook_id(
            public_webhook_id,
        )
        if configuration is None:
            raise WhatsAppRuntimeRoutingError(
                "WhatsApp webhook configuration was not resolved",
            )
        expected_configuration_id = configuration.id
        results: list[MessageProcessingResult] = []
        for status_event in payload.statuses:
            self._process_status(
                status_event,
                expected_configuration_id=expected_configuration_id,
                correlation_id=correlation_id,
            )

        for candidate in payload.messages:
            started = time.monotonic()
            context = self._resolve_expected(
                candidate.phone_number_id,
                expected_configuration_id,
            )
            message = self._mapper.map(candidate, context)
            if message is None:
                logger.info(
                    "whatsapp.message.unsupported",
                    correlation_id=str(correlation_id),
                    organization_id=str(context.organization_id),
                    bot_id=str(context.bot_id),
                    configuration_id=str(context.channel_configuration_id),
                    message_type=candidate.message_type,
                )
                results.append(MessageProcessingResult(status="ignored"))
                continue

            receipt = InboundMessageReceiptModel(
                id=uuid4(),
                channel_type=message.channel_type,
                external_message_id=message.external_message_id,
                organization_id=context.organization_id,
                bot_id=context.bot_id,
                channel_configuration_id=context.channel_configuration_id,
                status="received",
                attempt_count=0,
                received_at=self._now(),
                created_at=self._now(),
                updated_at=self._now(),
            )
            receipt, created = self._receipt_repository.create_or_get(receipt)
            self._session.commit()
            if (
                receipt.organization_id != context.organization_id
                or receipt.bot_id != context.bot_id
                or receipt.channel_configuration_id != context.channel_configuration_id
            ):
                raise WhatsAppRuntimeRoutingError(
                    "WhatsApp receipt identity does not match resolved channel",
                )
            if not created or not self._receipt_repository.acquire_for_processing(
                receipt.id,
            ):
                self._session.commit()
                logger.info(
                    "whatsapp.message.duplicate",
                    correlation_id=str(correlation_id),
                    receipt_id=str(receipt.id),
                    organization_id=str(context.organization_id),
                    bot_id=str(context.bot_id),
                    configuration_id=str(context.channel_configuration_id),
                    status=receipt.status,
                )
                results.append(
                    MessageProcessingResult(
                        status="duplicate",
                        receipt_id=receipt.id,
                    )
                )
                continue
            self._session.commit()
            logger.info(
                "whatsapp.message.processing_started",
                correlation_id=str(correlation_id),
                receipt_id=str(receipt.id),
                organization_id=str(context.organization_id),
                bot_id=str(context.bot_id),
                configuration_id=str(context.channel_configuration_id),
                message_type=candidate.message_type,
            )

            try:
                message = message.model_copy(
                    update={
                        "metadata": {
                            **message.metadata,
                            "receipt_id": str(receipt.id),
                        }
                    }
                )
                outbound = self._handler.handle(message)
                attempt_ids = ()
                if not outbound.metadata.get("handoff_blocked"):
                    attempt_ids = await self._send_outbound(
                        receipt.id,
                        context,
                        outbound,
                        correlation_id,
                    )
                self._receipt_repository.mark_processed(receipt.id, self._now())
                self._session.commit()
            except Exception:
                self._session.rollback()
                self._receipt_repository.mark_failed(
                    receipt.id,
                    "PROCESSING_FAILED",
                )
                self._session.commit()
                logger.error(
                    "whatsapp.message.processing_failed",
                    correlation_id=str(correlation_id),
                    receipt_id=str(receipt.id),
                    organization_id=str(context.organization_id),
                    bot_id=str(context.bot_id),
                    configuration_id=str(context.channel_configuration_id),
                    error_code="PROCESSING_FAILED",
                )
                results.append(
                    MessageProcessingResult(
                        status="failed",
                        receipt_id=receipt.id,
                        error_code="PROCESSING_FAILED",
                    )
                )
                continue

            logger.info(
                "whatsapp.message.processing_completed",
                correlation_id=str(correlation_id),
                receipt_id=str(receipt.id),
                organization_id=str(context.organization_id),
                bot_id=str(context.bot_id),
                configuration_id=str(context.channel_configuration_id),
                status="processed",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            results.append(
                MessageProcessingResult(
                    status="processed",
                    receipt_id=receipt.id,
                    outbound_attempt_ids=attempt_ids,
                )
            )
        return tuple(results)

    async def retry_attempt(
        self,
        attempt_id: UUID,
        *,
        correlation_id: UUID | None = None,
    ) -> bool:
        attempt = self._outbound_repository.get(attempt_id, for_update=True)
        if (
            attempt is None
            or attempt.status != "pending"
            or attempt.attempt_count >= self._max_attempts
            or (
                attempt.next_attempt_at is not None
                and attempt.next_attempt_at > self._now()
            )
        ):
            self._session.rollback()
            return False
        configuration = self._configuration_repository.get_scoped(
            attempt.channel_configuration_id,
            attempt.organization_id,
            attempt.bot_id,
        )
        if configuration is None:
            self._outbound_repository.mark_failed(
                attempt.id,
                "CHANNEL_UNAVAILABLE",
            )
            self._session.commit()
            return False
        context = ResolvedChannelContext(
            channel_type="whatsapp",
            organization_id=attempt.organization_id,
            bot_id=attempt.bot_id,
            channel_configuration_id=attempt.channel_configuration_id,
            external_channel_id=configuration.phone_number_id,
        )
        message = OutboundChannelMessage(
            channel_type="whatsapp",
            external_recipient_id=self._secret_cipher.decrypt(
                attempt.external_recipient_ciphertext,
            ),
            text=self._secret_cipher.decrypt(attempt.message_ciphertext),
            reply_to_external_message_id=attempt.reply_to_external_message_id,
        )
        await self._deliver(
            attempt.id,
            context,
            message,
            correlation_id or uuid4(),
        )
        return True

    async def _send_outbound(
        self,
        receipt_id: UUID,
        context: ResolvedChannelContext,
        outbound: OutboundChannelMessage,
        correlation_id: UUID,
    ) -> tuple[UUID, ...]:
        chunks = split_outbound_message(
            outbound,
            max_length=self._max_text_chars,
        )
        attempt_ids: list[UUID] = []
        for chunk in chunks:
            attempt = OutboundMessageAttemptModel(
                id=uuid4(),
                inbound_receipt_id=receipt_id,
                organization_id=context.organization_id,
                bot_id=context.bot_id,
                channel_configuration_id=context.channel_configuration_id,
                external_recipient_hash=_identifier_hash(
                    chunk.external_recipient_id,
                ),
                external_recipient_ciphertext=self._secret_cipher.encrypt(
                    chunk.external_recipient_id,
                ),
                message_ciphertext=self._secret_cipher.encrypt(chunk.text),
                reply_to_external_message_id=chunk.reply_to_external_message_id,
                status="pending",
                attempt_count=0,
                created_at=self._now(),
                updated_at=self._now(),
            )
            self._outbound_repository.create_pending(attempt)
            self._session.commit()
            attempt_ids.append(attempt.id)
            self._record_outbound(chunk, attempt, context)
            await self._deliver(
                attempt.id,
                context,
                chunk,
                correlation_id,
            )
            self._sync_outbound_attempt(attempt.id)
        return tuple(attempt_ids)

    def _record_outbound(
        self,
        message: OutboundChannelMessage,
        attempt: OutboundMessageAttemptModel,
        context: ResolvedChannelContext,
    ) -> None:
        if self._conversation_management is None:
            return
        conversation_id = message.metadata.get("conversation_id")
        if not isinstance(conversation_id, str):
            return
        self._conversation_management.record_outbound(
            message,
            UUID(conversation_id),
            context.organization_id,
            context.bot_id,
            attempt.id,
            self._now(),
        )

    def _sync_outbound_attempt(self, attempt_id: UUID) -> None:
        if self._conversation_management is None:
            return
        attempt = self._outbound_repository.get(attempt_id)
        if attempt is not None:
            self._conversation_management.sync_outbound_attempt(
                attempt.id,
                attempt.status,
                attempt.provider_message_id,
            )

    async def _deliver(
        self,
        attempt_id: UUID,
        context: ResolvedChannelContext,
        message: OutboundChannelMessage,
        correlation_id: UUID,
    ) -> None:
        attempt = self._outbound_repository.mark_attempt_started(attempt_id)
        self._session.commit()
        logger.info(
            "whatsapp.outbound.started",
            correlation_id=str(correlation_id),
            receipt_id=(
                str(attempt.inbound_receipt_id)
                if attempt.inbound_receipt_id is not None
                else None
            ),
            organization_id=str(context.organization_id),
            bot_id=str(context.bot_id),
            configuration_id=str(context.channel_configuration_id),
            status="pending",
        )
        try:
            delivery = await self._sender.send(message, context)
        except WhatsAppChannelDeliveryError as exc:
            if exc.retryable and attempt.attempt_count < self._max_attempts:
                delay = min(
                    self._retry_base_seconds * (2 ** max(attempt.attempt_count - 1, 0)),
                    self._retry_max_seconds,
                )
                self._outbound_repository.schedule_retry(
                    attempt_id,
                    exc.code,
                    self._now() + timedelta(seconds=delay),
                )
                final_status = "pending"
            else:
                self._outbound_repository.mark_failed(attempt_id, exc.code)
                final_status = "failed"
            self._session.commit()
            logger.warning(
                "whatsapp.outbound.failed",
                correlation_id=str(correlation_id),
                organization_id=str(context.organization_id),
                bot_id=str(context.bot_id),
                configuration_id=str(context.channel_configuration_id),
                status=final_status,
                error_code=exc.code,
            )
            return
        self._outbound_repository.mark_sent(
            attempt_id,
            delivery.provider_message_id,
            self._now(),
        )
        self._session.commit()
        logger.info(
            "whatsapp.outbound.sent",
            correlation_id=str(correlation_id),
            organization_id=str(context.organization_id),
            bot_id=str(context.bot_id),
            configuration_id=str(context.channel_configuration_id),
            status="sent",
        )

    def _process_status(
        self,
        status_event: WhatsAppStatusEvent,
        *,
        expected_configuration_id: UUID,
        correlation_id: UUID,
    ) -> None:
        context = self._resolve_expected(
            status_event.phone_number_id,
            expected_configuration_id,
        )
        attempt = self._outbound_repository.get_by_provider_message_id(
            status_event.provider_message_id,
        )
        if attempt is not None and (
            attempt.organization_id != context.organization_id
            or attempt.bot_id != context.bot_id
            or attempt.channel_configuration_id != context.channel_configuration_id
        ):
            raise WhatsAppRuntimeRoutingError(
                "WhatsApp status identity does not match outbound attempt",
            )
        updated = self._outbound_repository.update_provider_status(
            status_event.provider_message_id,
            status_event.status,
            status_event.timestamp,
            status_event.error_code,
        )
        self._session.commit()
        if updated and attempt is not None:
            self._sync_outbound_attempt(attempt.id)
        if updated:
            logger.info(
                "whatsapp.outbound.status_updated",
                correlation_id=str(correlation_id),
                organization_id=str(context.organization_id),
                bot_id=str(context.bot_id),
                configuration_id=str(context.channel_configuration_id),
                status=status_event.status,
                error_code=status_event.error_code,
            )

    def _resolve_expected(
        self,
        phone_number_id: str,
        expected_configuration_id: UUID,
    ) -> ResolvedChannelContext:
        try:
            context = self._resolver.resolve(phone_number_id)
        except ChannelResolutionError as exc:
            raise WhatsAppRuntimeRoutingError(
                "WhatsApp runtime channel was not resolved",
            ) from exc
        if context.channel_configuration_id != expected_configuration_id:
            raise WhatsAppRuntimeRoutingError(
                "WhatsApp webhook and channel identity do not match",
            )
        return context


def _identifier_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
