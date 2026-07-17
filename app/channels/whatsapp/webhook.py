from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from app.api.dependencies import get_conversation_service
from app.channels.whatsapp.adapter import WhatsAppAdapter
from app.channels.whatsapp.client import WhatsAppClient
from app.channels.whatsapp.models import WhatsAppWebhookPayload
from app.channels.whatsapp.sender import WhatsAppSender
from app.core.conversation.service import ConversationService
from app.infrastructure.settings import Settings, get_settings

router = APIRouter(tags=["whatsapp"])

adapter = WhatsAppAdapter()


def get_whatsapp_sender(
    settings: Annotated[Settings, Depends(get_settings)],
) -> WhatsAppSender:
    client = WhatsAppClient(settings)
    return WhatsAppSender(client)


@router.get("/webhooks/whatsapp", response_class=PlainTextResponse)
def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    settings: Annotated[Settings | None, Depends(get_settings)] = None,
) -> PlainTextResponse:
    if (
        hub_mode == "subscribe"
        and settings is not None
        and hub_verify_token == settings.whatsapp_webhook_verify_token
    ):
        return PlainTextResponse(str(hub_challenge))
    return PlainTextResponse("Verification failed", status_code=403)


@router.post("/webhooks/whatsapp", response_class=PlainTextResponse)
async def receive_webhook(
    payload: WhatsAppWebhookPayload,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    sender: Annotated[WhatsAppSender, Depends(get_whatsapp_sender)],
) -> PlainTextResponse:
    message = adapter.to_conversation_message(payload)
    if message is not None:
        response = service.handle_message(message)
        await sender.send(response, to=message.customer_id)
    return PlainTextResponse("OK")
