from app.domain.business.contracts import BusinessDecision
from app.domain.conversation.contracts import ChannelResponse


class ConversationMapper:
    def to_channel_response(self, decision: BusinessDecision) -> ChannelResponse:
        return ChannelResponse(
            status=decision.status,
            message=decision.message,
        )
