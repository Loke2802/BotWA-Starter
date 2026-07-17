from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str
    intent: str
    customer_id: str = ""
    company_id: str = ""


class KnowledgeContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: KnowledgeQuery
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KnowledgeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    found: bool
    content: str = ""
    confidence: str = "low"
