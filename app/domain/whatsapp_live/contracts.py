from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WhatsAppMessageType = Literal[
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
    "unknown",
]
InboundReceiptStatus = Literal["received", "processing", "processed", "failed"]
OutboundAttemptStatus = Literal[
    "pending",
    "sent",
    "delivered",
    "read",
    "failed",
]
WhatsAppProviderStatus = Literal["sent", "delivered", "read", "failed", "unknown"]


class WhatsAppInboundCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    external_message_id: str = Field(min_length=1, max_length=255)
    external_sender_id: str = Field(min_length=1, max_length=255)
    phone_number_id: str = Field(min_length=1, max_length=100)
    timestamp: datetime
    message_type: WhatsAppMessageType
    text: str | None = Field(default=None, max_length=65_536)


class WhatsAppStatusEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    provider_message_id: str = Field(min_length=1, max_length=255)
    phone_number_id: str = Field(min_length=1, max_length=100)
    status: WhatsAppProviderStatus
    timestamp: datetime
    error_code: str | None = Field(default=None, max_length=100)


class WhatsAppParsedWebhook(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    messages: tuple[WhatsAppInboundCandidate, ...] = ()
    statuses: tuple[WhatsAppStatusEvent, ...] = ()


class WhatsAppSendResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_message_id: str = Field(min_length=1, max_length=255)
