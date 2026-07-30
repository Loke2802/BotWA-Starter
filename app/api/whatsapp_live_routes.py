from typing import Annotated
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import PlainTextResponse

from app.api.whatsapp_configuration_dependencies import (
    get_whatsapp_webhook_validation_service,
)
from app.api.whatsapp_live_dependencies import (
    get_whatsapp_live_message_processor,
)
from app.application.whatsapp_configuration.webhook import (
    WhatsAppWebhookValidationError,
    WhatsAppWebhookValidationService,
)
from app.application.whatsapp_live.processor import (
    WhatsAppLiveMessageProcessor,
    WhatsAppRuntimeRoutingError,
)
from app.channels.whatsapp.live_mapper import (
    WhatsAppWebhookParser,
    WhatsAppWebhookPayloadError,
)
from app.infrastructure.settings import Settings, get_settings

router = APIRouter(tags=["whatsapp-live-messaging"])
logger = structlog.get_logger(__name__)


@router.post(
    "/webhooks/whatsapp/{public_webhook_id}",
    response_class=PlainTextResponse,
)
async def receive_configured_whatsapp_webhook(
    public_webhook_id: UUID,
    request: Request,
    validation_service: Annotated[
        WhatsAppWebhookValidationService,
        Depends(get_whatsapp_webhook_validation_service),
    ],
    processor: Annotated[
        WhatsAppLiveMessageProcessor,
        Depends(get_whatsapp_live_message_processor),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    signature: Annotated[
        str | None,
        Header(alias="X-Hub-Signature-256"),
    ] = None,
) -> PlainTextResponse:
    correlation_id = uuid4()
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = settings.whatsapp_webhook_max_body_bytes + 1
        if declared_size > settings.whatsapp_webhook_max_body_bytes:
            _log_rejected(correlation_id, public_webhook_id, "BODY_TOO_LARGE")
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="webhook payload is too large",
            )

    raw_body = await request.body()
    if len(raw_body) > settings.whatsapp_webhook_max_body_bytes:
        _log_rejected(correlation_id, public_webhook_id, "BODY_TOO_LARGE")
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="webhook payload is too large",
        )
    logger.info(
        "whatsapp.webhook.received",
        correlation_id=str(correlation_id),
        configuration_id=str(public_webhook_id),
        body_size=len(raw_body),
    )

    try:
        validation_service.verify_signature(
            public_webhook_id,
            raw_body=raw_body,
            signature_header=signature,
        )
    except WhatsAppWebhookValidationError as exc:
        _log_rejected(correlation_id, public_webhook_id, "SIGNATURE_INVALID")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="webhook signature is invalid",
        ) from exc

    try:
        payload = WhatsAppWebhookParser().parse(
            raw_body,
            max_events=settings.whatsapp_webhook_max_events,
        )
    except WhatsAppWebhookPayloadError as exc:
        _log_rejected(correlation_id, public_webhook_id, "PAYLOAD_INVALID")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid webhook payload",
        ) from exc

    try:
        await processor.process(
            payload,
            public_webhook_id=public_webhook_id,
            correlation_id=correlation_id,
        )
    except WhatsAppRuntimeRoutingError as exc:
        _log_rejected(correlation_id, public_webhook_id, "CHANNEL_NOT_RESOLVED")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="webhook channel was not resolved",
        ) from exc
    return PlainTextResponse("OK")


def _log_rejected(
    correlation_id: UUID,
    public_webhook_id: UUID,
    error_code: str,
) -> None:
    logger.warning(
        "whatsapp.webhook.rejected",
        correlation_id=str(correlation_id),
        configuration_id=str(public_webhook_id),
        error_code=error_code,
    )
