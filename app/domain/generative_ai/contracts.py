"""Provider-neutral, bounded contracts. Model output never grants authority."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NeedDefinition(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    question: str = Field(min_length=1, max_length=200)
    kind: Literal["text", "number"] = "text"
    required: bool = False
    attribute: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    comparison: Literal["equals", "contains", "range", "at_most"] = "equals"


class ResponseConfig(StrictModel):
    enabled: bool = False


class AIConfig(StrictModel):
    enabled: bool = False
    needs: list[NeedDefinition] = Field(default_factory=list, max_length=20)
    daily_jobs: int = Field(default=50, ge=1, le=500)
    conversational_response: ResponseConfig = Field(default_factory=ResponseConfig)

    @model_validator(mode="after")
    def unique_keys(self) -> "AIConfig":
        if len({item.key for item in self.needs}) != len(self.needs):
            raise ValueError("duplicate need key")
        return self


class Attribute(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=200)
    minimum: float | None = None
    maximum: float | None = None


class CatalogItem(StrictModel):
    name: str = Field(min_length=1, max_length=150)
    attributes: list[Attribute] = Field(max_length=30)

    @model_validator(mode="after")
    def unique_attributes(self) -> "CatalogItem":
        if len({item.key for item in self.attributes}) != len(self.attributes):
            raise ValueError("duplicate attribute key")
        for item in self.attributes:
            if (
                item.minimum is not None
                and item.maximum is not None
                and item.minimum > item.maximum
            ):
                raise ValueError("invalid attribute range")
        return self


class NeedPatch(StrictModel):
    key: str
    value: str = Field(min_length=1, max_length=150)
    message_ref: str
    quote: str = Field(min_length=1, max_length=300)


class Discovery(StrictModel):
    new_topic: bool
    needs: list[NeedPatch] = Field(max_length=20)
    search_terms: list[str] = Field(max_length=6)
    handoff_requested: bool

    @model_validator(mode="after")
    def bounded_terms(self) -> "Discovery":
        if any(len(term) > 100 for term in self.search_terms):
            raise ValueError("search term too long")
        if len({need.key for need in self.needs}) != len(self.needs):
            raise ValueError("duplicate need update")
        return self


class Match(StrictModel):
    need_key: str
    attribute_key: str


class Recommendation(StrictModel):
    item_ref: str
    matches: list[Match] = Field(min_length=1, max_length=10)


class KnowledgeQuote(StrictModel):
    source_ref: str
    quote: str = Field(min_length=1, max_length=800)


class AdviserResult(StrictModel):
    # Conversational transitions are deliberately constrained. Commercial facts
    # are rendered by the backend; there is no executable free-form reply field.
    tone: Literal["understood", "options", "clarify", "unknown"]
    question_key: str | None
    handoff_requested: bool
    recommendations: list[Recommendation] = Field(max_length=3)
    knowledge: list[KnowledgeQuote] = Field(max_length=2)


class Usage(StrictModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    model: str


class Generation(StrictModel):
    data: str
    usage: Usage


class ProviderError(RuntimeError):
    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(code)
        self.code, self.retryable = code, retryable
