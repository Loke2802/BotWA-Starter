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


class KnowledgeSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    name: str
    type: str = "in_memory"
    trust_level: float = 1.0
    status: str = "active"


class KnowledgeItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    content: str
    confidence: str = "low"
    source_trust_level: float = 1.0
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NormalizedKnowledgeItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    canonical_content: str
    confidence: str = "low"
    source_trust_level: float = 1.0
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    normalized_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ResolvedKnowledgeItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    sources: list[str] = Field(default_factory=list)
    content: str
    confidence: str = "low"
    resolution_strategy: str = "best_match"
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ValidatedKnowledgeItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str = ""
    content: str
    confidence: str = "low"
    health_score: float = 1.0
    validity_status: str = "approved"
    version: int = 1
    keywords: str = ""
    validated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KnowledgeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    found: bool
    content: str = ""
    confidence: str = "low"
    sources: list[str] = Field(default_factory=list)
    version: int = 1
