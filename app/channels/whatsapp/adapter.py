from uuid import UUID, uuid5

from app.channels.whatsapp.models import Message, WhatsAppWebhookPayload
from app.domain.conversation.contracts import ConversationMessage

WHATSAPP_NAMESPACE = UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")


def wa_id_to_conversation_id(wa_id: str) -> UUID:
    return uuid5(WHATSAPP_NAMESPACE, wa_id)


class WhatsAppAdapter:
    def to_conversation_message(
        self, payload: WhatsAppWebhookPayload
    ) -> ConversationMessage | None:
        for entry in payload.entry:
            for change in entry.changes:
                for msg in change.value.messages:
                    text_body = msg.get_text_body()
                    if not text_body:
                        continue
                    return self._map_message(
                        msg, text_body, change.value.metadata.phone_number_id
                    )
        return None

    def _map_message(
        self, msg: Message, text_body: str, phone_number_id: str
    ) -> ConversationMessage:
        return ConversationMessage(
            content=text_body,
            customer_id=msg.from_,
            company_id=phone_number_id,
            conversation_id=wa_id_to_conversation_id(msg.from_),
            channel="whatsapp",
            metadata={
                "message_id": msg.id,
                "timestamp": msg.timestamp,
                "phone_number_id": phone_number_id,
            },
        )
