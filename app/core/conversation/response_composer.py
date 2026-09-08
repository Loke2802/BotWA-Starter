from app.core.conversation.templates import template_for
from app.domain.business.contracts import BusinessDecision
from app.domain.conversation.contracts import ConversationContext
from app.domain.conversation.response import BusinessResponse


class ResponseComposer:
    def compose(
        self,
        decision: BusinessDecision,
        context: ConversationContext,
    ) -> BusinessResponse:
        message = decision.knowledge_content or template_for(decision.intent).message

        tone = template_for(decision.intent).tone

        return BusinessResponse(
            message=message,
            tone=tone,
            status=decision.status,
        )
