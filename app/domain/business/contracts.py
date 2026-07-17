from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BusinessRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    conversation_id: UUID


class BusinessContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    request: BusinessRequest
    intent: str


class BusinessDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    intent: str
    message: str
    confidence: str
    needs_knowledge: bool = False
