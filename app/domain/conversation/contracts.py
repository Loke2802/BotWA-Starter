from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ConversationMessage(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    content: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    conversation_id: UUID = Field(default_factory=uuid4)
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConversationContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: ConversationMessage

    context_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_message(cls, message: ConversationMessage) -> "ConversationContext":
        return cls(message=message)


class ChannelResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    message: str
