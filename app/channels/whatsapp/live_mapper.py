import json
from datetime import UTC, datetime
from typing import cast

from app.domain.channel.contracts import (
    InboundChannelMessage,
    ResolvedChannelContext,
)
from app.domain.whatsapp_live.contracts import (
    WhatsAppInboundCandidate,
    WhatsAppMessageType,
    WhatsAppParsedWebhook,
    WhatsAppProviderStatus,
    WhatsAppStatusEvent,
)

_MESSAGE_TYPES = frozenset(
    {
        "text",
        "image",
        "audio",
        "document",
        "video",
        "location",
        "contacts",
        "interactive",
        "button",
        "reaction",
    }
)
_PROVIDER_STATUSES = frozenset({"sent", "delivered", "read", "failed"})


class WhatsAppWebhookPayloadError(ValueError):
    pass


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.isdigit():
        raise ValueError("invalid event timestamp")
    return datetime.fromtimestamp(int(value), tz=UTC)


def _message_type(value: object) -> WhatsAppMessageType:
    if not isinstance(value, str) or value not in _MESSAGE_TYPES:
        return "unknown"
    return cast("WhatsAppMessageType", value)


def _provider_status(value: object) -> WhatsAppProviderStatus:
    if not isinstance(value, str) or value not in _PROVIDER_STATUSES:
        return "unknown"
    return cast("WhatsAppProviderStatus", value)


class WhatsAppWebhookParser:
    def parse(self, raw_body: bytes, *, max_events: int) -> WhatsAppParsedWebhook:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        try:
            payload = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WhatsAppWebhookPayloadError(
                "invalid WhatsApp webhook payload"
            ) from exc
        if not isinstance(payload, dict):
            raise WhatsAppWebhookPayloadError("invalid WhatsApp webhook payload")

        entries = payload.get("entry", [])
        if not isinstance(entries, list):
            raise WhatsAppWebhookPayloadError("invalid WhatsApp webhook entries")

        messages: list[WhatsAppInboundCandidate] = []
        statuses: list[WhatsAppStatusEvent] = []
        event_count = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            changes = entry.get("changes", [])
            if not isinstance(changes, list):
                continue
            for change in changes:
                if not isinstance(change, dict):
                    continue
                value = change.get("value")
                if not isinstance(value, dict):
                    continue
                metadata = value.get("metadata")
                if not isinstance(metadata, dict):
                    continue
                phone_number_id = metadata.get("phone_number_id")
                if not isinstance(phone_number_id, str) or not phone_number_id.strip():
                    continue
                event_count += self._map_messages(
                    value.get("messages"),
                    phone_number_id,
                    messages,
                )
                event_count += self._map_statuses(
                    value.get("statuses"),
                    phone_number_id,
                    statuses,
                )
                if event_count > max_events:
                    raise WhatsAppWebhookPayloadError(
                        "WhatsApp webhook event limit exceeded",
                    )
        return WhatsAppParsedWebhook(
            messages=tuple(messages),
            statuses=tuple(statuses),
        )

    @staticmethod
    def _map_messages(
        raw_messages: object,
        phone_number_id: str,
        messages: list[WhatsAppInboundCandidate],
    ) -> int:
        if raw_messages is None:
            return 0
        if not isinstance(raw_messages, list):
            return 1
        for raw_message in raw_messages:
            if not isinstance(raw_message, dict):
                continue
            try:
                message_id = raw_message["id"]
                sender_id = raw_message["from"]
                message_type = _message_type(raw_message.get("type"))
                if not isinstance(message_id, str) or not isinstance(sender_id, str):
                    continue
                text: str | None = None
                if message_type == "text":
                    text_data = raw_message.get("text")
                    if not isinstance(text_data, dict):
                        continue
                    body = text_data.get("body")
                    if not isinstance(body, str) or not body.strip():
                        continue
                    text = body
                messages.append(
                    WhatsAppInboundCandidate(
                        external_message_id=message_id,
                        external_sender_id=sender_id,
                        phone_number_id=phone_number_id,
                        timestamp=_timestamp(raw_message.get("timestamp")),
                        message_type=message_type,
                        text=text,
                    )
                )
            except (KeyError, ValueError):
                continue
        return len(raw_messages)

    @staticmethod
    def _map_statuses(
        raw_statuses: object,
        phone_number_id: str,
        statuses: list[WhatsAppStatusEvent],
    ) -> int:
        if raw_statuses is None:
            return 0
        if not isinstance(raw_statuses, list):
            return 1
        for raw_status in raw_statuses:
            if not isinstance(raw_status, dict):
                continue
            provider_message_id = raw_status.get("id")
            if not isinstance(provider_message_id, str):
                continue
            error_code: str | None = None
            errors = raw_status.get("errors")
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                code = errors[0].get("code")
                if isinstance(code, (str, int)):
                    error_code = str(code)[:100]
            try:
                statuses.append(
                    WhatsAppStatusEvent(
                        provider_message_id=provider_message_id,
                        phone_number_id=phone_number_id,
                        status=_provider_status(raw_status.get("status")),
                        timestamp=_timestamp(raw_status.get("timestamp")),
                        error_code=error_code,
                    )
                )
            except ValueError:
                continue
        return len(raw_statuses)


class WhatsAppInboundMessageMapper:
    def map(
        self,
        candidate: WhatsAppInboundCandidate,
        context: ResolvedChannelContext,
    ) -> InboundChannelMessage | None:
        if candidate.phone_number_id != context.external_channel_id:
            raise WhatsAppWebhookPayloadError("WhatsApp channel identity mismatch")
        if candidate.message_type != "text" or candidate.text is None:
            return None
        return InboundChannelMessage(
            channel_type="whatsapp",
            external_message_id=candidate.external_message_id,
            external_sender_id=candidate.external_sender_id,
            external_recipient_id=candidate.phone_number_id,
            text=candidate.text,
            timestamp=candidate.timestamp,
            resolved_context=context,
            metadata={"message_type": candidate.message_type},
        )
