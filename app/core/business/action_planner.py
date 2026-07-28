from app.domain.business.contracts import (
    ActionStep,
    BusinessActionPlan,
    BusinessConstraints,
    BusinessContext,
    BusinessDecision,
    BusinessIntent,
)


class ActionPlanner:
    def plan(
        self,
        context: BusinessContext,
        business_intent: BusinessIntent,
        constraints: BusinessConstraints,
        decision: BusinessDecision,
    ) -> BusinessActionPlan:
        if not constraints.is_feasible:
            return BusinessActionPlan(
                steps=[
                    ActionStep(
                        action="escalate",
                        target="human_support",
                        parameters={
                            "intent": business_intent.name,
                            "reason": self._build_reason(constraints),
                        },
                        order=1,
                    ),
                ],
                total_steps=1,
            )

        intent = business_intent.name

        if intent in ("greeting", "farewell", "thanks"):
            return self._respond_plan(intent, context)

        if intent in ("price_inquiry", "support", "question"):
            return self._knowledge_aware_plan(intent, context, decision)

        if intent == "unknown":
            return self._respond_plan(intent, context)

        return self._respond_plan(intent, context)

    def _respond_plan(
        self,
        intent: str,
        context: BusinessContext,
    ) -> BusinessActionPlan:
        return BusinessActionPlan(
            steps=[
                ActionStep(
                    action="respond",
                    target="conversation_service",
                    parameters={
                        "intent": intent,
                        "content": context.request.content,
                    },
                    order=1,
                ),
            ],
            total_steps=1,
        )

    def _knowledge_aware_plan(
        self,
        intent: str,
        context: BusinessContext,
        decision: BusinessDecision,
    ) -> BusinessActionPlan:
        if decision.needs_knowledge and decision.knowledge_content is None:
            return BusinessActionPlan(
                steps=[
                    ActionStep(
                        action="query_knowledge",
                        target="knowledge_service",
                        parameters={
                            "intent": intent,
                            "content": context.request.content,
                        },
                        order=1,
                    ),
                    ActionStep(
                        action="respond",
                        target="conversation_service",
                        parameters={
                            "intent": intent,
                            "content": context.request.content,
                        },
                        order=2,
                    ),
                ],
                total_steps=2,
            )
        return self._respond_plan(intent, context)

    def _build_reason(self, constraints: BusinessConstraints) -> str:
        reasons = []
        for c in constraints.constraints:
            if c.applies and c.reason:
                reasons.append(c.reason)
        return "; ".join(reasons) if reasons else "no_feasible_route"
