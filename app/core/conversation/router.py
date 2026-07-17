from app.core.business.service import BusinessBrainService
from app.domain.business.contracts import BusinessDecision, BusinessRequest
from app.domain.conversation.contracts import ConversationContext


class MessageRouter:
    def __init__(self, business_brain: BusinessBrainService) -> None:
        self._business_brain = business_brain

    def route(self, context: ConversationContext) -> BusinessDecision:
        request = BusinessRequest(
            content=context.message.content,
            customer_id=context.message.customer_id,
            company_id=context.message.company_id,
            conversation_id=context.message.conversation_id,
        )
        return self._business_brain.process(request)
