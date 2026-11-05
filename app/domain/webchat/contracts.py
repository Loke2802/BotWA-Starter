from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WebchatMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=1500)
    idempotency_key: UUID


class WebchatMessage(BaseModel):
    id: UUID
    role: Literal["user", "assistant", "operator"]
    text: str


class WebchatHistory(BaseModel):
    messages: list[WebchatMessage]
    status: Literal["bot_active", "waiting_human", "human_active", "resolved"]


class WebchatSession(BaseModel):
    token: str
    expires_at: datetime


class WebchatError(ValueError):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        super().__init__(detail)
