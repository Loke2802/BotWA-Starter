import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


def is_business_scoped_user_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Z]{2}\.[A-Za-z0-9]{1,128}", value) is not None
    )


class AdviserAlertConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recipient: str = Field(pattern=r"^[1-9][0-9]{7,14}$", repr=False)
    template_name: str = Field(pattern=r"^[a-z0-9_]{1,128}$")
    language: str = Field(pattern=r"^[a-z]{2,3}(_[A-Z]{2})?$")
    portal_origin: str

    @field_validator("portal_origin")
    @classmethod
    def validate_portal_origin(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username is not None
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
            or any(character.isspace() for character in value)
        ):
            raise ValueError("an HTTPS portal origin is required")
        return value.rstrip("/")


class WhatsAppTemplateMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9_]{1,128}$")
    language: str = Field(pattern=r"^[a-z]{2,3}(_[A-Z]{2})?$")
    parameters: tuple[str, str, str] = Field(repr=False)


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
    ad_source_id: str | None = Field(default=None, pattern=r"^[0-9]{1,64}$")
    username: str | None = Field(
        default=None, repr=False, pattern=r"^[a-zA-Z0-9_.]{1,64}$"
    )


class WhatsAppStatusEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    provider_message_id: str = Field(min_length=1, max_length=255)
    phone_number_id: str = Field(min_length=1, max_length=100)
    status: WhatsAppProviderStatus
    timestamp: datetime
    error_code: str | None = Field(default=None, max_length=100)


class WhatsAppBusinessAppEcho(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    external_message_id: str = Field(min_length=1, max_length=255)
    external_recipient_id: str = Field(min_length=1, max_length=255)
    phone_number_id: str = Field(min_length=1, max_length=100)
    timestamp: datetime
    message_type: str = Field(min_length=1, max_length=50)
    text: str | None = Field(default=None, max_length=65_536)


class WhatsAppParsedWebhook(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    messages: tuple[WhatsAppInboundCandidate, ...] = ()
    statuses: tuple[WhatsAppStatusEvent, ...] = ()
    echoes: tuple[WhatsAppBusinessAppEcho, ...] = ()


class WhatsAppSendResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_message_id: str = Field(min_length=1, max_length=255)
