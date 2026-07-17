from pydantic import BaseModel, ConfigDict

from app.domain.conversation.contracts import ConversationContext


class BusinessBrainStubResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    message: str


class BusinessBrainStub:
    def accept(self, context: ConversationContext) -> BusinessBrainStubResponse:
        return BusinessBrainStubResponse(
            status="accepted",
            message="Business Brain not implemented.",
        )
