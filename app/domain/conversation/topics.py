from pydantic import BaseModel, ConfigDict, Field


class ConversationTopic(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    confidence: str
    is_primary: bool = True


class ConversationTopics(BaseModel):
    model_config = ConfigDict(frozen=True)

    primary: ConversationTopic | None = None
    secondary: list[ConversationTopic] = Field(default_factory=list)
