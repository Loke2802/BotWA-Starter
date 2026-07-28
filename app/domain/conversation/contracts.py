from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.conversation.state import ConversationState
from app.domain.conversation.topics import ConversationTopics


class ConversationMessage(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    content: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    conversation_id: UUID = Field(default_factory=uuid4)
    channel: str = Field(default="http")
    metadata: dict[str, object] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HistoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str
    content: str
    created_at: datetime


class ConversationContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: ConversationMessage
    context_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    state: ConversationState | None = None
    history: list[HistoryEntry] = Field(default_factory=list)
    customer_profile: dict[str, object] = Field(default_factory=dict)
    channel_metadata: dict[str, object] = Field(default_factory=dict)
    topics: ConversationTopics | None = None


class ChannelResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    message: str
