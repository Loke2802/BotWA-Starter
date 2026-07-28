from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationState(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversation_id: UUID
    current_state: str
    previous_state: str | None = None
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)
