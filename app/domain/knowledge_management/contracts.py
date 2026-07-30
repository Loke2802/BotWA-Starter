from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

KnowledgeEntryStatus = Literal["draft", "published", "archived"]
KnowledgeSourceType = Literal["manual"]


def _non_empty(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty")
    return cleaned


class KnowledgeEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    bot_id: UUID
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20_000)
    status: KnowledgeEntryStatus = "draft"
    source_type: KnowledgeSourceType = "manual"
    metadata: dict[str, object] = Field(default_factory=dict)
    created_by_user_id: UUID
    updated_by_user_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _non_empty(value, "title")

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return _non_empty(value, "content")


class KnowledgeEntryCreate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20_000)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _non_empty(value, "title")

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return _non_empty(value, "content")


class KnowledgeEntryUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=20_000)
    metadata: dict[str, object] | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        return None if value is None else _non_empty(value, "title")

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str | None) -> str | None:
        return None if value is None else _non_empty(value, "content")


class KnowledgeEntryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    knowledge_entry: KnowledgeEntry


class KnowledgeEntryListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[KnowledgeEntry]
    total: int
    page: int
    page_size: int
