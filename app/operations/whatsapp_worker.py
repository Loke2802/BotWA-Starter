"""Recover committed inbox/outbox work without re-executing completed messages."""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import uuid4

import structlog
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.api.whatsapp_live_dependencies import (
    get_whatsapp_cloud_api_client,
    get_whatsapp_live_message_processor,
)
from app.application.whatsapp_live.processor import (
    WhatsAppLiveMessageProcessor,
    WhatsAppRuntimeRoutingError,
)
from app.domain.whatsapp_live.contracts import (
    WhatsAppInboundCandidate,
    WhatsAppParsedWebhook,
)
from app.infrastructure.database import SessionLocal
from app.infrastructure.logging import configure_logging
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.models.whatsapp_message_transport import (
    InboundMessageReceiptModel as Inbox,
)
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel as Outbox,
)
from app.infrastructure.settings import get_settings
from app.operations.automation_worker import install_shutdown_handlers
from app.security.secret_cipher import EnvironmentSecretCipher, SecretCipher

logger = structlog.get_logger(__name__)


async def recover_batch(
    session: Session,
    processor: WhatsAppLiveMessageProcessor,
    cipher: SecretCipher,
    *,
    limit: int = 20,
    max_attempts: int = 3,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(UTC)
    # Delivery might have reached Meta before the process died. Never blindly
    # resend an expired claim: preserve a terminal, actionable unknown outcome.
    expired = list(
        session.scalars(
            update(Outbox)
            .execution_options(synchronize_session="fetch")
            .where(
                Outbox.status == "pending",
                Outbox.delivery_token.is_not(None),
                Outbox.delivery_started_at < now - timedelta(minutes=5),
            )
            .values(
                status="failed", last_error_code="DELIVERY_UNKNOWN", delivery_token=None
            )
            .returning(Outbox.id)
        )
    )
    session.commit()
    for attempt_id in expired:
        processor._sync_outbound_attempt(attempt_id)
    pending = list(
        session.scalars(
            select(Inbox.id)
            .join(
                WhatsAppChannelConfigurationModel,
                WhatsAppChannelConfigurationModel.id == Inbox.channel_configuration_id,
            )
            .where(
                WhatsAppChannelConfigurationModel.status == "active",
                WhatsAppChannelConfigurationModel.webhook_enabled.is_(True),
                Inbox.status.in_(("received", "failed")),
                Inbox.payload_ciphertext.is_not(None),
                Inbox.attempt_count < max_attempts,
                or_(Inbox.next_attempt_at.is_(None), Inbox.next_attempt_at <= now),
            )
            .order_by(Inbox.received_at, Inbox.id)
            .limit(limit)
        )
    )
    for receipt_id in pending:
        receipt = session.get(Inbox, receipt_id)
        if receipt is None or not receipt.payload_ciphertext:
            continue
        config = session.get(
            WhatsAppChannelConfigurationModel, receipt.channel_configuration_id
        )
        if config is None or config.status != "active" or not config.webhook_enabled:
            continue
        try:
            candidate = WhatsAppInboundCandidate.model_validate_json(
                cipher.decrypt(receipt.payload_ciphertext)
            )
            await processor.process(
                WhatsAppParsedWebhook(messages=(candidate,)),
                public_webhook_id=config.public_webhook_id,
                correlation_id=uuid4(),
            )
        except WhatsAppRuntimeRoutingError:
            session.rollback()
            logger.warning(
                "whatsapp.recovery.channel_unavailable", receipt_id=str(receipt_id)
            )
        except ValueError:
            session.rollback()
            session.execute(
                update(Inbox)
                .where(
                    Inbox.id == receipt_id,
                    Inbox.status.in_(("received", "failed")),
                )
                .values(
                    status="failed",
                    attempt_count=max_attempts,
                    last_error_code="INVALID_RECOVERY_PAYLOAD",
                )
            )
            session.commit()
            logger.error(
                "whatsapp.recovery.invalid_payload", receipt_id=str(receipt_id)
            )
    attempts = list(
        session.scalars(
            select(Outbox.id)
            .where(
                Outbox.status == "pending",
                Outbox.delivery_token.is_(None),
                Outbox.attempt_count < max_attempts,
                or_(Outbox.next_attempt_at.is_(None), Outbox.next_attempt_at <= now),
            )
            .order_by(Outbox.created_at, Outbox.id)
            .limit(limit)
        )
    )
    for attempt_id in attempts:
        await processor.retry_attempt(attempt_id)
    return len(pending) + len(attempts)


async def run_once(limit: int) -> int:
    settings = get_settings()
    cipher = EnvironmentSecretCipher.from_settings(settings)
    with SessionLocal() as session:
        processor = get_whatsapp_live_message_processor(
            session, cipher, get_whatsapp_cloud_api_client(settings), settings
        )
        return await recover_batch(
            session,
            processor,
            cipher,
            limit=limit,
            max_attempts=settings.whatsapp_outbound_max_attempts,
        )


def main() -> None:
    configure_logging(get_settings().log_level)
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--batch-size", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 100:
        parser.error("batch-size must be between 1 and 100")
    stop = Event()
    install_shutdown_handlers(stop)
    while not stop.is_set():
        try:
            asyncio.run(run_once(args.batch_size))
        except Exception:
            # No exception payload: provider, ciphertext and DB errors can contain PII.
            logger.error("whatsapp.recovery.failed", error_code="RECOVERY_FAILED")
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            break
        stop.wait(1)


if __name__ == "__main__":
    main()
