from app.core.business.policy import BusinessPolicy
from app.domain.business.contracts import BusinessContext, BusinessDecision


class DecisionEngine:
    def __init__(self, policy: BusinessPolicy) -> None:
        self._policy = policy

    def evaluate(self, context: BusinessContext) -> BusinessDecision:
        response = self._policy.get_response(context.intent)
        return BusinessDecision(
            status=response["status"],
            intent=context.intent,
            message=response["message"],
            confidence=response["confidence"],
            needs_knowledge=response["needs_knowledge"],
        )
