from app.domain.conversation.contracts import ChannelResponse


def to_whatsapp_text_payload(response: ChannelResponse, to: str) -> dict[str, object]:
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": response.message},
    }
