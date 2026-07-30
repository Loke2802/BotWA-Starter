import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from app.application.channel.conversation_handler import ChannelConversationHandler
from app.application.channel.text_splitter import split_outbound_message
from app.application.knowledge_management.provider import BotKnowledgeProvider
from app.channels.whatsapp.live_mapper import (
    WhatsAppInboundMessageMapper,
    WhatsAppWebhookParser,
    WhatsAppWebhookPayloadError,
)
from app.core.conversation.service import ConversationService
from app.domain.channel.contracts import (
    InboundChannelMessage,
    OutboundChannelMessage,
    ResolvedChannelContext,
)
from app.domain.conversation.contracts import ChannelResponse, ConversationMessage


class RecordingConversationService:
    def __init__(self) -> None:
        self.messages: list[ConversationMessage] = []

    def handle_message(self, message: ConversationMessage) -> ChannelResponse:
        self.messages.append(message)
        return ChannelResponse(status="accepted", message="Respuesta segura")


class RecordingKnowledgeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object, str | None]] = []

    def retrieve_published(
        self,
        organization_id: object,
        bot_id: object,
        *,
        search: str | None = None,
        limit: int = 20,
    ) -> list[object]:
        assert limit == 20
        self.calls.append((organization_id, bot_id, search))
        return []


def context() -> ResolvedChannelContext:
    return ResolvedChannelContext(
        channel_type="whatsapp",
        organization_id=uuid4(),
        bot_id=uuid4(),
        channel_configuration_id=uuid4(),
        external_channel_id="123456789",
    )


def payload(*messages: dict[str, object], statuses: object = None) -> bytes:
    value: dict[str, object] = {
        "metadata": {"phone_number_id": "123456789"},
        "messages": list(messages),
    }
    if statuses is not None:
        value["statuses"] = statuses
    return json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [{"changes": [{"field": "messages", "value": value}]}],
        }
    ).encode()


def text_message(message_id: str = "wamid.1") -> dict[str, object]:
    return {
        "from": "51999999999",
        "id": message_id,
        "timestamp": "1785384000",
        "type": "text",
        "text": {"body": "Necesito soporte"},
    }


def test_parser_maps_multiple_events_and_statuses_without_raw_payload() -> None:
    raw = payload(
        text_message(),
        {
            "from": "51999999999",
            "id": "wamid.image",
            "timestamp": "1785384001",
            "type": "image",
            "image": {"id": "media-sensitive"},
        },
        statuses=[
            {
                "id": "provider.1",
                "status": "delivered",
                "timestamp": "1785384002",
            }
        ],
    )

    parsed = WhatsAppWebhookParser().parse(raw, max_events=10)

    assert len(parsed.messages) == 2
    assert parsed.messages[0].message_type == "text"
    assert parsed.messages[0].text == "Necesito soporte"
    assert parsed.messages[1].message_type == "image"
    assert parsed.messages[1].text is None
    assert parsed.statuses[0].status == "delivered"
    assert "media-sensitive" not in parsed.model_dump_json()


def test_parser_skips_malformed_event_but_keeps_valid_sibling() -> None:
    raw = payload(
        {"id": "broken", "type": "text"},
        text_message("wamid.valid"),
    )

    parsed = WhatsAppWebhookParser().parse(raw, max_events=10)

    assert [message.external_message_id for message in parsed.messages] == [
        "wamid.valid"
    ]


def test_parser_rejects_global_malformed_and_event_limit() -> None:
    parser = WhatsAppWebhookParser()

    with pytest.raises(WhatsAppWebhookPayloadError):
        parser.parse(b"not-json", max_events=10)
    with pytest.raises(WhatsAppWebhookPayloadError):
        parser.parse(payload(text_message(), text_message("wamid.2")), max_events=1)


def test_mapper_processes_text_and_ignores_supported_non_text() -> None:
    parser = WhatsAppWebhookParser()
    mapped = parser.parse(
        payload(
            text_message(),
            {
                "from": "51999999999",
                "id": "wamid.audio",
                "timestamp": "1785384001",
                "type": "audio",
            },
        ),
        max_events=10,
    )
    mapper = WhatsAppInboundMessageMapper()

    inbound = mapper.map(mapped.messages[0], context())

    assert inbound is not None
    assert inbound.text == "Necesito soporte"
    assert inbound.metadata == {"message_type": "text"}
    assert mapper.map(mapped.messages[1], context()) is None


def test_mapper_rejects_phone_identity_mismatch() -> None:
    candidate = (
        WhatsAppWebhookParser()
        .parse(
            payload(text_message()),
            max_events=10,
        )
        .messages[0]
    )
    wrong_context = context().model_copy(
        update={"external_channel_id": "987654321"},
    )

    with pytest.raises(WhatsAppWebhookPayloadError):
        WhatsAppInboundMessageMapper().map(candidate, wrong_context)


def test_channel_handler_passes_generic_identity_to_conversation_and_knowledge() -> (
    None
):
    resolved = context()
    inbound = InboundChannelMessage(
        channel_type="whatsapp",
        external_message_id="wamid.1",
        external_sender_id="51999999999",
        external_recipient_id=resolved.external_channel_id,
        text="Necesito soporte",
        timestamp=datetime(2026, 7, 30, tzinfo=UTC),
        resolved_context=resolved,
    )
    conversation = RecordingConversationService()
    knowledge = RecordingKnowledgeProvider()
    handler = ChannelConversationHandler(
        cast("ConversationService", conversation),
        cast("BotKnowledgeProvider", knowledge),
    )

    outbound = handler.handle(inbound)

    assert outbound.text == "Respuesta segura"
    assert outbound.reply_to_external_message_id == "wamid.1"
    assert len(conversation.messages) == 1
    core_message = conversation.messages[0]
    assert core_message.company_id == str(resolved.organization_id)
    assert core_message.channel == "whatsapp"
    assert core_message.metadata["bot_id"] == str(resolved.bot_id)
    assert knowledge.calls == [
        (resolved.organization_id, resolved.bot_id, "Necesito soporte")
    ]


def test_long_message_split_is_deterministic_and_unicode_safe() -> None:
    message = OutboundChannelMessage(
        channel_type="whatsapp",
        external_recipient_id="51999999999",
        text="áéíóú mensaje largo con palabras",
    )

    chunks = split_outbound_message(message, max_length=10)

    assert chunks
    assert all(chunk.text and len(chunk.text) <= 10 for chunk in chunks)
    assert " ".join(chunk.text for chunk in chunks) == message.text


def test_core_engines_do_not_import_whatsapp_live_modules() -> None:
    forbidden = (
        "whatsapp_live",
        "channels.whatsapp",
        "whatsapp_configuration",
    )
    core_sources = (
        list(Path("app/core").rglob("*.py"))
        + list(Path("app/domain/business").rglob("*.py"))
        + list(Path("app/domain/conversation").rglob("*.py"))
        + list(Path("app/domain/knowledge").rglob("*.py"))
        + list(Path("app/domain/automation").rglob("*.py"))
        + list(Path("app/domain/integration").rglob("*.py"))
    )

    for source in core_sources:
        text = source.read_text(encoding="utf-8")
        assert all(term not in text for term in forbidden), source
